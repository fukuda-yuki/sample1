"""Research-side, fixed-upstream Responses relay. Never log prompts or credentials.

Deploy on two networks: one private worker network and one outbound network.
Only the gateway receives the read-only auth file; workers receive no credential.
"""
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import uuid

LOCK = threading.Lock()


def record(name, event):
    with LOCK:
        with (Path('/usage') / name).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event) + '\n')


def validate_request(body, model, effort):
    if body.get('model') != model:
        raise ValueError('model_mismatch')
    if body.get('reasoning', {}).get('effort') != effort:
        raise ValueError('effort_mismatch')
    if not body.get('stream'):
        raise ValueError('stream_required')
    if body.get('background') or body.get('store'):
        raise ValueError('stored_background_requests_forbidden')
    def check_tool(tool):
        if tool.get('type') not in ('function', 'custom', 'namespace'):
            raise ValueError('remote_tool_forbidden')
        for nested in tool.get('tools', []):
            check_tool(nested)
    for tool in body.get('tools', []):
        check_tool(tool)
    def check_remote_input(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('image_url', 'file_url') and isinstance(child, str) and not child.startswith('data:'):
                    raise ValueError('remote_input_forbidden')
                check_remote_input(child)
        elif isinstance(value, list):
            for child in value:
                check_remote_input(child)
    check_remote_input(body.get('input'))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path != '/responses':
            self.send_error(403, 'Endpoint denied')
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 32 * 1024 * 1024:
                raise ValueError('invalid_size')
            raw = self.rfile.read(size)
            body = json.loads(raw)
            validate_request(body, os.environ['MODEL_ID'], os.environ['EFFORT'])
        except (ValueError, KeyError) as error:
            self.send_error(403, 'Request policy denied: ' + str(error))
            return
        request_id = str(uuid.uuid4())
        event = {'run_id': os.environ['RUN_ID'], 'session_id': 'implementation',
                 'parent_session_id': None, 'event_id': request_id, 'request_id': request_id,
                 'timestamp': datetime.now(timezone.utc).isoformat(),
                 'model_id': os.environ['MODEL_ID'], 'source': 'fixed-upstream-gateway',
                 'provider': 'openai-chatgpt-codex', 'mode': 'request', 'usage': None,
                 'includes_children': False, 'status': 'unknown'}
        record('started.jsonl', event)
        try:
            auth = json.loads(Path('/secrets/auth.json').read_text())['tokens']
            headers = {'Authorization': 'Bearer ' + auth['access_token'],
                       'ChatGPT-Account-Id': auth['account_id'],
                       'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                       'User-Agent': 'codex_cli_rs/0.153.0', 'originator': 'codex_cli_rs',
                       'OpenAI-Beta': 'responses=experimental'}
            connection = http.client.HTTPSConnection('chatgpt.com', timeout=300)
            connection.request('POST', '/backend-api/codex/responses', body=raw, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            self.send_header('Content-Type', response.getheader('Content-Type', 'text/event-stream'))
            self.send_header('Connection', 'close')
            self.end_headers()
            event['http_status'] = response.status
            while True:
                line = response.readline()
                if not line:
                    break
                if line.startswith(b'data: '):
                    try:
                        item = json.loads(line[6:])
                        if item.get('type') in ('response.completed', 'response.failed', 'response.incomplete'):
                            data = item.get('response', {})
                            usage = data.get('usage')
                            if usage is not None:
                                event['usage'] = {key: usage[key] for key in (
                                    'input_tokens', 'output_tokens', 'total_tokens',
                                    'input_tokens_details', 'output_tokens_details') if key in usage}
                            event['status'] = item['type']
                            event['provider_response_id'] = data.get('id')
                            event['response_model_id'] = data.get('model')
                    except (ValueError, TypeError):
                        pass
                try:
                    self.wfile.write(line)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    # Keep collecting usage after the consumer has disconnected.
                    pass
            connection.close()
        except (OSError, KeyError, ValueError, http.client.HTTPException):
            event['status'] = 'gateway_or_upstream_error'
        finally:
            record('events.jsonl', event)
            self.close_connection = True


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()

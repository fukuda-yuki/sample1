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
SEND_LOCK = threading.Lock()
FAILURE_LOCK = threading.Lock()
FAILED = threading.Event()


def signal_503(event, response):
    """Called at headers, before reading or forwarding a possibly stalled body."""
    if os.environ.get('MODEL_HTTP_503_POLICY') not in ('stop_run', 'stop_run_and_cleanup'):
        return
    with FAILURE_LOCK:
        if FAILED.is_set():
            return
        FAILED.set()
        failure = {k: event.get(k) for k in ('run_id', 'request_id', 'provider', 'model_id')}
        failure.update(experiment_id=os.environ.get('EXPERIMENT_ID'), http_status=503,
            detected_at=datetime.now(timezone.utc).isoformat(), stop_trigger='model_http_503',
            retry_after=response.getheader('Retry-After'))
        root = Path(os.environ.get('USAGE_DIRECTORY', '/usage'))
        temporary = root / ('provider-failure.' + str(uuid.uuid4()) + '.tmp')
        with temporary.open('x') as stream:
            json.dump(failure, stream); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(root / 'provider-failure.json')


def record(name, event):
    with LOCK:
        with (Path(os.environ.get('USAGE_DIRECTORY', '/usage')) / name).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event) + '\n')
            stream.flush()
            os.fsync(stream.fileno())


def validate_request(body, model, effort, wire='responses'):
    if body.get('model') != model:
        raise ValueError('model_mismatch')
    if (body.get('reasoning', {}).get('effort') if wire == 'responses' else body.get('reasoning_effort')) != effort:
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
    check_remote_input(body.get('input') if wire == 'responses' else body.get('messages'))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        wire = os.environ.get('WIRE_API', 'responses')
        endpoint = '/responses' if wire == 'responses' else '/chat/completions'
        if self.path != endpoint:
            self.send_error(403, 'Endpoint denied')
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 32 * 1024 * 1024:
                raise ValueError('invalid_size')
            raw = self.rfile.read(size)
            body = json.loads(raw)
            validate_request(body, os.environ['MODEL_ID'], os.environ.get('EFFORT') or None, wire)
        except (ValueError, KeyError) as error:
            self.send_error(403, 'Request policy denied: ' + str(error))
            return
        request_id = str(uuid.uuid4())
        event = {'run_id': os.environ['RUN_ID'], 'session_id': 'implementation',
                 'parent_session_id': None, 'event_id': request_id, 'request_id': request_id,
                 'timestamp': datetime.now(timezone.utc).isoformat(),
                 'model_id': os.environ['MODEL_ID'], 'source': 'fixed-upstream-gateway',
                 'provider': os.environ.get('PROVIDER', 'openai-chatgpt-codex'), 'mode': 'request', 'usage': None,
                 'includes_children': False, 'status': 'unknown'}
        if event['provider'] in ('opencode-zen', 'opencode-go'):
            event['provider_session_id'] = event['run_id']
        admitted = False
        try:
            if event['provider'] in ('opencode-zen', 'opencode-go'):
                # Only the gateway mounts this file. No credential in argv/env/logs.
                key = Path('/secrets/zen-key').read_text().strip()
                if not key:
                    raise ValueError('missing_key')
                headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                           'Accept': 'text/event-stream',
                           'User-Agent': 'sample1-copilot-gateway/1',
                           'x-opencode-session': event['provider_session_id']}
                connection = http.client.HTTPSConnection('opencode.ai', timeout=300)
                upstream_path = ('/zen/go/v1' if event['provider'] == 'opencode-go' else '/zen/v1') + endpoint
            else:
                auth = json.loads(Path('/secrets/auth.json').read_text())['tokens']
                headers = {'Authorization': 'Bearer ' + auth['access_token'],
                       'ChatGPT-Account-Id': auth['account_id'],
                       'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                       'User-Agent': 'codex_cli_rs/0.153.0', 'originator': 'codex_cli_rs',
                       'OpenAI-Beta': 'responses=experimental'}
                connection = http.client.HTTPSConnection('chatgpt.com', timeout=300)
                upstream_path = '/backend-api/codex/responses'
            with SEND_LOCK:
                if FAILED.is_set():
                    record('control.jsonl', {'run_id':event['run_id'], 'reason':'blocked_after_503',
                                            'request_id':request_id})
                    event['status'] = 'local_blocked_after_503'
                    self.send_error(503, 'Run stopped after upstream 503')
                    return
                record('started.jsonl', event)
                admitted = True
                # Durable logging can wait for another writer or fsync. A 503
                # received during that wait cancels this still-unsent request.
                if FAILED.is_set():
                    event['status'] = 'local_cancelled_before_send_after_503'
                    self.send_error(503, 'Run stopped after upstream 503')
                    return
                connection.request('POST', upstream_path, body=raw, headers=headers)
            response = connection.getresponse()
            event['http_status'] = response.status
            if response.status == 503:
                signal_503(event, response)
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
                        if wire == 'completions':
                            if item.get('model'):
                                event['response_model_id'] = item['model']
                                event['provider_response_id'] = item.get('id')
                                if item['model'] != os.environ['MODEL_ID']:
                                    event['policy_error'] = 'response_model_mismatch'
                                    break
                            usage = item.get('usage')
                            if usage is not None:
                                event['native_usage'] = usage
                                event['usage'] = {'input_tokens':usage.get('prompt_tokens'),
                                    'output_tokens':usage.get('completion_tokens'),
                                    'total_tokens':usage.get('total_tokens')}
                                event['status'] = 'chat.completed'
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
                            if event['response_model_id'] != os.environ['MODEL_ID']:
                                event['policy_error'] = 'response_model_mismatch'
                                # Retain consumed usage, but do not deliver a fallback answer.
                                break
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
            if admitted:
                record('events.jsonl', event)
            self.close_connection = True


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()

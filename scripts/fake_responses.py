"""Keyless synthetic Responses fixture. Never forwards any request."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    count = 0
    def log_message(self, *args):
        pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        Handler.count += 1
        n = Handler.count
        numeric={'run_id':os.environ['RUN_ID'],'session_id':'implementation','event_id':f'fixture-{n}',
                 'request_id':f'fixture-{n}','model_id':body['model'],'provider':'synthetic-responses',
                 'mode':'request','usage':None}
        with Path('/telemetry/started.jsonl').open('a') as f:f.write(json.dumps(numeric)+'\n')
        tools = [t.get('name') for t in body.get('tools', [])]
        with Path('/telemetry/requests.jsonl').open('a') as f:
            f.write(json.dumps({'request': n, 'model': body.get('model'), 'tools': tools,
                'policy':{k:body[k] for k in ('model','stream','reasoning','store','background') if k in body}}) + '\n')
        item = ({'id': 'fc_1', 'type': 'function_call', 'call_id': 'call_1', 'name': 'bash',
                 'arguments': json.dumps({'command': 'printf 42 > /workspace/probe.txt; cat /workspace/probe.txt',
                                          'description': 'Write and read synthetic probe'})}
                if n == 1 else {'id': 'msg_2', 'type': 'message', 'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': 'Observed 42.', 'annotations': []}]})
        response = {'id': f'resp_{n}', 'object': 'response', 'model': body['model'], 'status': 'completed',
                    'output': [item], 'usage': {'input_tokens': 10*n, 'output_tokens': 3}}
        with Path('/telemetry/events.jsonl').open('a') as f:
            f.write(json.dumps(dict(numeric,provider_response_id=response['id'],usage=response['usage']))+'\n')
        events = [{'type': 'response.created', 'response': dict(response, status='in_progress', output=[])},
                  {'type': 'response.output_item.added', 'output_index': 0, 'item': dict(item, arguments='') if n == 1 else item}]
        if n == 1:
            events += [{'type': 'response.function_call_arguments.delta', 'item_id': 'fc_1',
                        'output_index': 0, 'delta': item['arguments']},
                       {'type': 'response.function_call_arguments.done', 'item_id': 'fc_1',
                        'output_index': 0, 'arguments': item['arguments']}]
        else:
            events += [{'type': 'response.output_text.delta', 'item_id': 'msg_2', 'output_index': 0,
                        'content_index': 0, 'delta': 'Observed 42.'}]
        events += [{'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                   {'type': 'response.completed', 'response': response}]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for seq, event in enumerate(events):
            self.wfile.write(('data: ' + json.dumps(dict(event, sequence_number=seq)) + '\n\n').encode())
        self.wfile.flush()


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()

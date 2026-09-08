import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from model_gateway import Handler
from gateway_usage import collect
from run_copilot import worker_command, worker_environment, validate_config, execute


class GatewayTests(unittest.TestCase):
    def request(self, terminal, status=200, wrong=False):
        with tempfile.TemporaryDirectory() as directory:
            env = {'MODEL_ID': 'muse-test-contributor-free', 'RUN_ID': 'run', 'PROVIDER': 'opencode-zen',
                   'USAGE_DIRECTORY': directory, 'EFFORT': ''}
            response = io.BytesIO(terminal)
            response.status = status
            response.getheader = lambda *a: 'text/event-stream'
            with patch.dict('os.environ', env), patch('model_gateway.http.client.HTTPSConnection') as connection, \
                    patch('model_gateway.Path.read_text', return_value='never-save-this-key'):
                connection.return_value.getresponse.return_value = response
                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    req = urllib.request.Request('http://127.0.0.1:%s/responses' % server.server_port,
                        json.dumps({'model': 'wrong' if wrong else env['MODEL_ID'], 'stream': True}).encode(),
                        headers={'Content-Type': 'application/json'})
                    try:
                        urllib.request.urlopen(req, timeout=5).read()
                    except urllib.error.HTTPError as error:
                        error.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()
                if not wrong:
                    headers = connection.return_value.request.call_args.kwargs['headers']
                    self.assertEqual(headers['x-opencode-session'], env['RUN_ID'])
                    self.assertEqual(headers['User-Agent'], 'sample1-copilot-gateway/1')
            text = ''.join(p.read_text() for p in Path(directory).glob('*.jsonl'))
            self.assertNotIn('never-save-this-key', text)
            return collect(Path(directory)), text

    def test_usage_and_model_mismatch_and_429_and_broken_stream(self):
        for model, complete in [('muse-test-contributor-free', True), ('other', False)]:
            data = {'type': 'response.completed', 'response': {'id': 'resp-1', 'model': model,
                     'usage': {'input_tokens': 10, 'output_tokens': 2}}}
            summary, _ = self.request(('data: ' + json.dumps(data) + '\n\n').encode())
            self.assertEqual(summary['usage_complete'], complete)
            self.assertEqual(summary['observed_tokens'], 12)
        for body, status in [(b'', 429), (b'data: {broken', 200)]:
            summary, text = self.request(body, status)
            self.assertFalse(summary['usage_complete'])
            self.assertIsNone(summary['total_tokens'])
            self.assertIn('http_status', text)
        summary, text = self.request(b'', wrong=True)
        self.assertFalse(summary['usage_complete'])
        self.assertEqual(text, '')

    def test_worker_has_no_condition_secret_resume_or_delegation(self):
        c = {'model_id': 'muse-test-contributor-free', 'experiment_id': 'opaque', 'phase': 'comparison'}
        env = worker_environment(c, 'uuid')
        cmd = worker_command(c, 'uuid')
        encoded = json.dumps([cmd, env])
        for forbidden in ('normal', 'anti', 'COPILOT_OFFLINE', 'API_KEY', '--resume', 'task,', 'web_fetch'):
            self.assertNotIn(forbidden, encoded)
        self.assertIn('responses', encoded)
        self.assertNotIn('effort', encoded)

if __name__ == '__main__':
    unittest.main()

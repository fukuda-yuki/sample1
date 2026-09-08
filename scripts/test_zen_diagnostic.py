import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zen_diagnostic import MODEL, request, run


class DiagnosticTests(unittest.TestCase):
    def test_new_uuid_header_and_rejection_preserved_without_secret(self):
        with tempfile.TemporaryDirectory() as root:
            outputs = []
            sessions = []
            for status in (400, 429):
                with patch('zen_diagnostic.credential', return_value=('secret-not-to-persist', 'test')), \
                        patch('zen_diagnostic.request', side_effect=[
                            (200, json.dumps({'data': [{'id': MODEL}]}).encode()),
                            (status, b"OpenCode's free tier can only be used in OpenCode secret-not-to-persist")]) as call:
                    output = run(root)
                    sessions.append(call.call_args.kwargs['session_id'])
                    result = json.loads((output / 'result.json').read_text())
                    manifest = json.loads((output / 'manifest.json').read_text())
                    self.assertEqual(sessions[-1], manifest['provider_session_id'])
                    self.assertEqual(sessions[-1], result['run_id'])
                    self.assertEqual(result['model_requests_started'], 1)
                    self.assertIsNone(result['usage'])
                    self.assertEqual(result['status'], 'rate_limited' if status == 429 else 'free_tier_restricted_to_opencode')
                    outputs.append(output)
            self.assertNotEqual(*sessions)
            self.assertTrue(all(p.exists() for p in outputs))
            self.assertNotIn('secret-not-to-persist', ''.join(p.read_text() for p in Path(root).rglob('*.json')))

    def test_honest_identity_and_session_header_on_wire(self):
        with patch('zen_diagnostic.http.client.HTTPSConnection') as factory:
            factory.return_value.getresponse.return_value.read.return_value = b'{}'
            session = '70075fed-73b9-4fda-8705-221e4df0d157'
            request('test-key', 'POST', '/zen/v1/responses', '{}', session)
            headers = factory.return_value.request.call_args.kwargs['headers']
            self.assertEqual(headers['x-opencode-session'], session)
            self.assertEqual(headers['User-Agent'], 'sample1-research-diagnostic/1')
            self.assertNotIn('x-opencode-client', headers)

    def test_absent_exact_model_never_calls_model(self):
        with tempfile.TemporaryDirectory() as root, \
                patch('zen_diagnostic.credential', return_value=('test', 'test')), \
                patch('zen_diagnostic.request', return_value=(200, b'{"data": []}')) as call:
            output = run(root)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(json.loads((output / 'result.json').read_text())['model_requests_started'], 0)


if __name__ == '__main__':
    unittest.main()

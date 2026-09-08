import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zen_diagnostic import MODEL, request, run


class DiagnosticTests(unittest.TestCase):
    def diagnostic(self, payload, status=200, headers=None):
        with tempfile.TemporaryDirectory() as root, \
                patch('zen_diagnostic.credential', return_value=('secret-not-to-persist', 'test')), \
                patch('zen_diagnostic.request', side_effect=[
                    (200, {}, json.dumps({'data': [{'id': MODEL}]}).encode()),
                    (status, headers or {}, payload if isinstance(payload, bytes) else json.dumps(payload).encode())]) as call:
            output = run(root)
            result = json.loads((output / 'result.json').read_text())
            self.assertEqual(call.call_count, 2)
            self.assertNotIn('secret-not-to-persist', (output / 'result.json').read_text())
            return result

    def test_response_and_usage_are_both_required(self):
        valid = {'model': MODEL, 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}],
                 'usage': {'input_tokens': 2, 'output_tokens': 1, 'total_tokens': 3}}
        result = self.diagnostic(valid)
        self.assertEqual(result['status'], 'response_received')
        self.assertEqual(result['response_text'], 'OK')
        self.assertEqual(result['usage'], valid['usage'])
        for change, expected in [({'output': []}, 'response_text_missing'),
                                  ({'output': [{'type': 'reasoning'}]}, 'response_text_missing'),
                                  ({'model': 'other'}, 'response_model_mismatch'),
                                  ({'usage': None}, 'usage_missing'),
                                  ({'usage': {}}, 'usage_missing')]:
            with self.subTest(change=change):
                self.assertEqual(self.diagnostic(dict(valid, **change))['status'], expected)
        for name, value in [('input_tokens', -1), ('output_tokens', True), ('total_tokens', 4), ('input_tokens', '2')]:
            with self.subTest(name=name, value=value):
                self.assertEqual(self.diagnostic(dict(valid, usage=dict(valid['usage'], **{name: value})))['status'], 'usage_invalid')
        for malformed in (b'{broken', b'null', b'[]', b'{"output": null}'):
            self.assertEqual(self.diagnostic(malformed)['status'], 'diagnostic_transport_or_format_error')

    def test_429_metadata_and_cause_are_separate_and_redacted(self):
        for message, cause in [('insufficient balance secret-not-to-persist', 'account_balance_or_quota'),
                                ('Please try later', 'upstream_rejected')]:
            result = self.diagnostic({'error': {'code': 'quota', 'type': 'limit', 'message': message}}, 429,
                                     {'Retry-After': '30', 'X-Request-ID': 'id-secret-not-to-persist', 'Set-Cookie': 'secret'})
            self.assertEqual(result['cause'], cause)
            self.assertEqual(result['response_http_status'], 429)
            self.assertEqual(result['response_headers']['retry-after'], '30')
            self.assertNotIn('set-cookie', result['response_headers'])
            self.assertEqual(result['error']['code'], 'quota')
        result = self.diagnostic(b'Bearer other-token ' + b'x' * 2000, 500)
        self.assertNotIn('other-token', result['error']['message'])
        self.assertLessEqual(len(result['error']['message']), 1024)

    def test_timeout_preserves_started_request_without_retry(self):
        with tempfile.TemporaryDirectory() as root, \
                patch('zen_diagnostic.credential', return_value=('secret', 'test')), \
                patch('zen_diagnostic.request', side_effect=[
                    (200, {}, json.dumps({'data': [{'id': MODEL}]}).encode()), TimeoutError('secret')]) as call:
            result = json.loads((run(root) / 'result.json').read_text())
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['model_requests_started'], 1)
            self.assertEqual(result['error_type'], 'TimeoutError')
            self.assertIsNone(result['usage'])

    def test_new_uuid_header_and_rejection_preserved_without_secret(self):
        with tempfile.TemporaryDirectory() as root:
            outputs = []
            sessions = []
            for status in (400, 429):
                with patch('zen_diagnostic.credential', return_value=('secret-not-to-persist', 'test')), \
                        patch('zen_diagnostic.request', side_effect=[
                            (200, {}, json.dumps({'data': [{'id': MODEL}]}).encode()),
                            (status, {}, b"OpenCode's free tier can only be used in OpenCode secret-not-to-persist")]) as call:
                    output = run(root)
                    sessions.append(call.call_args.kwargs['session_id'])
                    result = json.loads((output / 'result.json').read_text())
                    manifest = json.loads((output / 'manifest.json').read_text())
                    self.assertEqual(sessions[-1], manifest['provider_session_id'])
                    self.assertEqual(sessions[-1], result['run_id'])
                    self.assertEqual(result['model_requests_started'], 1)
                    self.assertIsNone(result['usage'])
                    self.assertEqual(result['status'], 'upstream_rejected')
                    self.assertEqual(result['cause'], 'free_tier_restricted_to_opencode')
                    self.assertEqual(result['rate_limited'], status == 429)
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
                patch('zen_diagnostic.request', return_value=(200, {}, b'{"data": []}')) as call:
            output = run(root)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(json.loads((output / 'result.json').read_text())['model_requests_started'], 0)


if __name__ == '__main__':
    unittest.main()

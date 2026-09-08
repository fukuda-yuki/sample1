import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import provider_diagnostic as diagnostic


class MatrixTests(unittest.TestCase):
    def test_fixed_targets_and_payloads(self):
        self.assertEqual(sum(map(len,diagnostic.MATRIX.values())),5)
        for provider,targets in diagnostic.MATRIX.items():
            for model,api in targets:
                body=diagnostic.body_for(model,api)
                self.assertEqual(body['model'],model)
                self.assertEqual(body.get('max_tokens',body.get('max_output_tokens')),256)
                self.assertFalse(body['stream'])
                self.assertEqual(body.get('input',(body.get('messages') or [{}])[0].get('content')),'Reply with OK.')

    def test_deadline_kills_request_without_retry(self):
        with patch('provider_diagnostic.subprocess.run',side_effect=subprocess.TimeoutExpired('probe',30)) as call:
            self.assertEqual(diagnostic.bounded_exchange('zen','models',Path('unused')),'request_deadline_exceeded')
            self.assertEqual(call.call_count,1)
            self.assertEqual(call.call_args.kwargs['timeout'],30)

    def test_provider_destination_credential_and_headers(self):
        for provider,targets in diagnostic.MATRIX.items():
            with tempfile.TemporaryDirectory() as d:
                directory=Path(d)/'70075fed-73b9-4fda-8705-221e4df0d157';directory.mkdir()
                with patch('provider_diagnostic.credential',return_value=('test-secret','test')) as key, \
                     patch('provider_diagnostic.http.client.HTTPSConnection') as connection:
                    response=connection.return_value.getresponse.return_value
                    response.status=429;response.getheaders.return_value=[('Retry-After','30'),('Set-Cookie','test-secret')]
                    response.read.return_value=b'{"error":{"message":"test-secret Bearer secret-token"}}'
                    model,api=targets[0];diagnostic.exchange(provider,api,directory,model)
                    self.assertEqual(connection.call_args.args[0],diagnostic.PROVIDERS[provider][0])
                    self.assertEqual(key.call_args.args[0],diagnostic.PROVIDERS[provider][2])
                    self.assertTrue(key.call_args.kwargs['windows_user_only'])
                    headers=connection.return_value.request.call_args.kwargs['headers']
                    self.assertEqual('x-opencode-session' in headers,provider=='zen')
                    self.assertEqual(headers['User-Agent'],'sample1-research-diagnostic/1')
                saved=''.join(p.read_text() for p in directory.glob('*'))
                self.assertNotIn('test-secret',saved);self.assertNotIn('secret-token',saved)

    def test_parallel_providers_serial_requests_failure_continues_and_openai_hold(self):
        barrier=threading.Barrier(2);active=set();guard=threading.Lock();calls=[]
        def probe(provider,api,root,model=None):
            with guard:
                self.assertNotIn(provider,active);active.add(provider);calls.append((provider,api,model))
            if api=='models': barrier.wait(timeout=3)
            time.sleep(.005)
            with guard: active.remove(provider)
            return ({'diagnostic_id':'list-'+provider,'provider':provider,'http_status':200 if not model else 429},
                    {'data':[{'id':m} for m,_ in diagnostic.MATRIX[provider]]})
        with tempfile.TemporaryDirectory() as d,patch('provider_diagnostic.probe',side_effect=probe):
            rows=diagnostic.run(Path(d)/'trial')
        self.assertEqual(len(rows),5)
        self.assertEqual(sum(bool(m) for _,_,m in calls),3)
        self.assertEqual([m for p,_,m in calls if p=='zen' and m],[m for m,_ in diagnostic.MATRIX['zen']])
        self.assertTrue(all(r['end_reason']=='openai_free_application_unconfirmed' for r in rows if r['provider']=='openai'))

    def test_missing_model_is_skipped_and_other_models_continue(self):
        def probe(provider,api,root,model=None):
            return {'diagnostic_id':'list','http_status':200}, {'data':[{'id':diagnostic.MATRIX['zen'][1][0]}]}
        with tempfile.TemporaryDirectory() as d,patch('provider_diagnostic.probe',side_effect=probe) as call:
            rows=diagnostic.provider_run('zen',Path(d))
            self.assertEqual(call.call_count,2)
            self.assertEqual(rows[0]['end_reason'],'model_list_check_failed')

    def test_usage_limit_and_no_text_distinctions(self):
        for api in ('responses','chat/completions'):
            usage={'input_tokens':2,'output_tokens':1,'total_tokens':3} if api=='responses' else {'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}
            data={'model':'model','usage':usage,'status':'completed','output':[{'content':[{'type':'output_text','text':'OK'}]}],
                  'choices':[{'message':{'content':'OK'},'finish_reason':'stop'}]}
            self.assertEqual(diagnostic.interpret(data,'model',api)['end_reason'],'response_received')
            data.update(status='incomplete',incomplete_details={'reason':'max_output_tokens'},
                        choices=[{'message':{'content':''},'finish_reason':'length'}])
            self.assertEqual(diagnostic.interpret(data,'model',api)['end_reason'],'output_limit_reached')

    def test_confirmed_openai_runs_both_apis_once_even_after_failure(self):
        calls=[]
        def probe(provider,api,root,model=None):
            calls.append(api)
            return {'diagnostic_id':'fixture','http_status':200 if not model else 500}, {'data':[{'id':diagnostic.MATRIX['openai'][0][0]}]}
        with tempfile.TemporaryDirectory() as d,patch('provider_diagnostic.probe',side_effect=probe):
            diagnostic.provider_run('openai',Path(d),True)
        self.assertEqual(calls,['models','responses','chat/completions'])

    def test_masked_authentication_echo_is_fully_redacted(self):
        from zen_diagnostic import sanitized
        result=sanitized('Incorrect API key provided: sk-proj.******tail. You can find it.','actual-key')
        self.assertNotIn('tail',result)
        self.assertNotIn('sk-proj',result)


if __name__=='__main__':unittest.main()

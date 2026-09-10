import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import model_gateway as gateway
from gateway_usage import collect


class Protocols(unittest.TestCase):
    def test_503_during_durable_start_log_cancels_unsent_request(self):
        gateway.FAILED.clear()
        with tempfile.TemporaryDirectory() as temporary:
            env={'MODEL_ID':'muse-spark-1.2-contributor','RUN_ID':'run-race','PROVIDER':'opencode-go',
                 'WIRE_API':'responses','USAGE_DIRECTORY':temporary,'EFFORT':''}
            original=gateway.record
            def delayed_record(name,event):
                original(name,event)
                if name=='started.jsonl':gateway.FAILED.set()
            with patch.dict('os.environ',env),patch('model_gateway.Path.read_text',return_value='fixture-secret'), \
                    patch('model_gateway.record',side_effect=delayed_record),patch('model_gateway.http.client.HTTPSConnection') as upstream:
                server=ThreadingHTTPServer(('127.0.0.1',0),gateway.Handler)
                thread=threading.Thread(target=server.serve_forever);thread.start()
                try:
                    request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/responses',
                        json.dumps({'model':env['MODEL_ID'],'stream':True}).encode())
                    with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
                    self.assertEqual(caught.exception.code,503);caught.exception.close()
                    upstream.return_value.request.assert_not_called()
                finally:server.shutdown();server.server_close();thread.join()
            event=json.loads((Path(temporary)/'events.jsonl').read_text())
            self.assertEqual(event['status'],'local_cancelled_before_send_after_503')
            self.assertIsNone(event['usage'])
        gateway.FAILED.clear()

    def exercise(self,wire,body,*,status=200,stall=False):
        gateway.FAILED.clear()
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);release=threading.Event()
            class Response(io.BytesIO):
                def readline(self,*args):
                    if stall:release.wait(5)
                    return super().readline(*args)
                def getheader(self,key,default=None):return '1' if key=='Retry-After' else 'text/event-stream'
            response=Response(body);response.status=status
            env={'MODEL_ID':'omen-alpha' if wire=='completions' else 'muse-spark-1.2-contributor',
                 'RUN_ID':'run-a','EXPERIMENT_ID':'experiment-a','PROVIDER':'opencode-go',
                 'WIRE_API':wire,'MODEL_HTTP_503_POLICY':'stop_run_and_cleanup','USAGE_DIRECTORY':temporary,'EFFORT':'','PRESERVE_MODEL_RESPONSES':'1'}
            with patch.dict('os.environ',env),patch('model_gateway.Path.read_text',return_value='fixture-secret'),patch('model_gateway.http.client.HTTPSConnection') as upstream:
                upstream.return_value.getresponse.return_value=response
                server=ThreadingHTTPServer(('127.0.0.1',0),gateway.Handler)
                thread=threading.Thread(target=server.serve_forever);thread.start()
                endpoint='/chat/completions' if wire=='completions' else '/responses'
                def request():
                    req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+endpoint,
                        json.dumps({'model':env['MODEL_ID'],'stream':True}).encode())
                    try:
                        with urllib.request.urlopen(req,timeout=8) as result:return result.read()
                    except urllib.error.HTTPError as error:
                        error.close();return b''
                try:
                    if stall:
                        client=threading.Thread(target=request);client.start()
                        deadline=time.monotonic()+3
                        while not (directory/'provider-failure.json').exists() and time.monotonic()<deadline:time.sleep(.01)
                        self.assertTrue((directory/'provider-failure.json').exists(),'503 not signalled at headers')
                        self.assertFalse(release.is_set())
                        request()
                        self.assertEqual(upstream.return_value.request.call_count,1,'new upstream request after 503')
                        release.set();client.join(5);self.assertFalse(client.is_alive())
                    else:self.assertEqual(request(),body if status==200 else b'')
                    self.assertEqual(upstream.return_value.request.call_args.args[1],'/zen/go/v1'+endpoint)
                finally:
                    release.set();server.shutdown();server.server_close();thread.join()
            events=[json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
            text=''.join(p.read_text() for p in directory.glob('*.json*'))
            self.assertNotIn('fixture-secret',text)
            spools=list((directory/'responses').glob('*.sse'))
            self.assertEqual(len(spools),1)
            self.assertEqual(spools[0].read_bytes(),body.replace(b'fixture-secret',b'[REDACTED]'))
            result=collect(directory)
            failure=json.loads((directory/'provider-failure.json').read_text()) if (directory/'provider-failure.json').exists() else None
            gateway.FAILED.clear()
            return result,events,failure

    def test_chat_tool_stream_and_continuation_usage(self):
        for delta in ({'tool_calls':[{'index':0,'id':'call-1','type':'function','function':{'name':'shell','arguments':'{"command":"pwd"}'}}]}, {'content':'Complete'}):
            chunks=[{'id':'chat-1','model':'omen-alpha','choices':[{'index':0,'delta':delta,'finish_reason':'tool_calls' if 'tool_calls' in delta else 'stop'}]},
                    {'id':'chat-1','model':'omen-alpha','choices':[],'usage':{'prompt_tokens':13,'completion_tokens':7,'total_tokens':20}}]
            body=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
            result,events,_=self.exercise('completions',body)
            self.assertTrue(result['usage_complete']);self.assertEqual(result['total_tokens'],20)
            self.assertEqual(events[0]['native_usage']['prompt_tokens'],13)

    def test_chat_missing_usage_remains_null(self):
        result,_,_=self.exercise('completions',b'data: [DONE]\n\n')
        self.assertFalse(result['usage_complete']);self.assertIsNone(result['total_tokens'])

    def test_echoed_secret_is_redacted_only_in_saved_response(self):
        self.exercise('completions',b'data: {"content":"fixture-secret"}\n\ndata: [DONE]\n\n')

    def test_503_at_headers_stops_only_new_requests_for_both_protocols(self):
        for wire in ('responses','completions'):
            result,events,failure=self.exercise(wire,b'overloaded',status=503,stall=True)
            self.assertEqual(failure['run_id'],'run-a');self.assertEqual(failure['experiment_id'],'experiment-a')
            self.assertEqual(failure['http_status'],503);self.assertEqual(len(events),1)
            self.assertIsNone(result['total_tokens'])

    def test_non503_does_not_emit_stop_signal(self):
        for status in (429,500,504):
            _,_,failure=self.exercise('completions',b'failure',status=status)
            self.assertIsNone(failure)

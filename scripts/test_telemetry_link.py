import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from telemetry_link import native_to_otlp, inventory, reconcile, atomic
from run_experiment import snapshot


def fixture(root, run_id=None, experiment_id=None, *, sessions=2):
    run_id, experiment_id = run_id or str(uuid.uuid4()), experiment_id or str(uuid.uuid4())
    (root / 'telemetry').mkdir(parents=True)
    (root / 'raw-usage').mkdir()
    (root / 'frozen').mkdir()
    (root / 'frozen/probe.txt').write_text('synthetic')
    atomic(root / 'snapshot.json', snapshot(root / 'frozen'))
    atomic(root / 'manifest.json', {'run_id':run_id,'experiment_id':experiment_id,'processes_stopped':True,
           'submission_fixed':True,'phase':'comparison','experiment_version':'copilot-synthetic',
           'condition':'normal','distribution':{'condition':'normal'},'end_reason':'agent_completed'})
    native, starts, ends = [], [], []
    for n in range(sessions):
        trace = uuid.uuid4().hex
        session = str(uuid.uuid4())
        root_span = uuid.uuid4().hex[:16]
        resource = {'attributes':{'run.id':run_id,'experiment.id':experiment_id,'client.kind':'copilot-cli'}}
        base = {'type':'span','traceId':trace,'spanId':root_span,'name':'invoke_agent',
                'kind':0,'startTime':[1,0],'endTime':[2,0],'resource':resource,
                'attributes':{'gen_ai.conversation.id':session,'gen_ai.operation.name':'invoke_agent',
                              'gen_ai.usage.input_tokens':9999},'status':{'code':0}}
        native.append(base)
        response = 'resp_' + uuid.uuid4().hex
        native.append(dict(base,spanId=uuid.uuid4().hex[:16],parentSpanId=root_span,name='chat muse',
                           attributes={'gen_ai.conversation.id':session,'gen_ai.operation.name':'chat',
                                       'gen_ai.response.id':response,'gen_ai.usage.input_tokens':10+n,
                                       'gen_ai.usage.output_tokens':3}))
        event = {'run_id':run_id,'session_id':'implementation','event_id':str(uuid.uuid4()),'mode':'request',
                 'usage':None,'model_id':'muse-fixture','provider':'opencode-zen'}
        event['request_id'] = event['event_id']
        starts.append(event)
        ends.append(dict(event,provider_response_id=response,usage={'input_tokens':10+n,'output_tokens':3}))
    for path, rows in [('telemetry/native.jsonl',native),('raw-usage/started.jsonl',starts),('raw-usage/events.jsonl',ends)]:
        (root/path).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return run_id, experiment_id


class LinkTests(unittest.TestCase):
    def test_parent_missing_does_not_erase_gateway_total_in_new_projection(self):
        from telemetry_link import project_measurement, selected_measurement
        from preserve import digest
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'run';fixture(root)
            path=root/'telemetry/native.jsonl'
            lines=[json.loads(l) for l in path.read_text().splitlines()]
            path.write_text(''.join(json.dumps(e)+'\n' for e in lines if e['attributes']['gen_ai.operation.name']=='chat'))
            atomic(root/'usage.json',{'usage_complete':False,'total_tokens':None})
            atomic(root/'telemetry-link.json',{'status':'readback_verified'})
            old=(root/'usage.json').read_bytes()
            output=root/'measurements'/'new-processing'
            result=project_measurement(root,output)
            self.assertEqual(result['total_tokens'],27)
            self.assertTrue(result['usage_complete'])
            self.assertTrue(result['native_calls']['verified'])
            self.assertFalse(result['trace_structure']['complete'])
            self.assertEqual((root/'usage.json').read_bytes(),old)
            atomic(root/'measurement-ref.json',{'path':'measurements/new-processing/measurement.json','sha256':digest(output/'measurement.json')})
            self.assertEqual(selected_measurement(root),result)
            with (root/'raw-usage/events.jsonl').open('a') as f:f.write('\n')
            with self.assertRaises(ValueError):selected_measurement(root)

    def test_multiple_traces_retry_dedupe_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            rid,eid=fixture(root)
            path=root/'telemetry/native.jsonl'
            original=path.read_text()
            path.write_text(original+original+json.dumps({'type':'metric','name':'tokens'})+'\n')
            payload,ignored,problems=native_to_otlp(path)
            items=inventory(payload,rid,eid)
            usage,sessions,relations,calls=reconcile(root/'raw-usage',items,rid)
            self.assertEqual(usage['total_tokens'],27)
            self.assertEqual(len(sessions),2)
            self.assertEqual(len(calls),2)
            self.assertEqual(ignored,{'metric':1})
            with self.assertRaises(ValueError): inventory(payload,'different',eid)
            events=root/'raw-usage/events.jsonl'
            events.write_text(events.read_text().splitlines()[0]+'\n')
            usage,*_=reconcile(root/'raw-usage',items,rid)
            self.assertIsNone(usage['total_tokens'])
            self.assertEqual(usage['observed_tokens'],13)

    def test_corrupt_parent_and_conflicting_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); rid,eid=fixture(root)
            path=root/'telemetry/native.jsonl'
            with path.open('a') as f:f.write('{broken')
            payload,_,problems=native_to_otlp(path)
            self.assertTrue(problems)
            items=inventory(payload,rid,eid)
            first=next(iter(items));items.pop(first)
            usage,*_=reconcile(root/'raw-usage',items,rid)
            self.assertIsNone(usage['total_tokens'])
            bad=copy.deepcopy(payload['resourceSpans'][0]);bad['scopeSpans'][0]['spans'][0]['name']='different'
            payload['resourceSpans'].append(bad)
            with self.assertRaises(ValueError):inventory(payload,rid,eid)

if __name__=='__main__':unittest.main()

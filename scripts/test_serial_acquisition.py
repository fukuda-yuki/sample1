import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from copilot_parallel import make_plan, load, dispatch, extend
from serial_acquisition import MODELS, next_model, slot_config, next_slot
from preserve import read
from telemetry_link import atomic


class SerialAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'batch'
        self.config = dict(batch_schema=2,phase='data-acquisition',experiment_version='copilot-acquisition-test',
                           repetitions_per_condition=10,max_parallel=1,model_id=MODELS[0],
                           authorization_file=str(Path(self.temp.name)/'scope.json'),synthetic=True)
        atomic(Path(self.config['authorization_file']),{'preservation':{'archive':{'linux':self.temp.name,'windows':self.temp.name}}})
        make_plan(self.root,self.config,20260910)

    def test_exact_twenty_reproducible_balanced_slots(self):
        from copilot_parallel import slots
        c,i=load(self.root)
        self.assertEqual(len(i['runs']),20)
        self.assertEqual([r['condition'] for r in i['runs']],[r['condition'] for r in slots(20260910,1,10)])
        self.assertEqual(sum(r['condition']=='anti' for r in i['runs']),10)
        self.assertEqual(next_slot(self.root,c,i),i['runs'][0])
        with self.assertRaises(ValueError):extend(self.root,11)

    def test_dispatch_cannot_increase_parallelism_or_limit(self):
        for k,limit in ((2,1),(1,2),(None,1),(1,None)):
            with self.subTest(k=k,limit=limit),self.assertRaises(ValueError):
                dispatch(self.root,lambda *a:self.fail('must not launch'),k=k,limit=limit)

    def test_fallback_only_503_and_returns_to_base(self):
        self.assertEqual(next_model(None),MODELS[0])
        for first,second in zip(MODELS,MODELS[1:]):
            self.assertEqual(next_model(dict(model_id=first,end_reason='provider_unavailable',stop_trigger='model_http_503')),second)
        with self.assertRaises(ValueError):next_model(dict(model_id=MODELS[-1],end_reason='provider_unavailable',stop_trigger='model_http_503'))
        with self.assertRaises(ValueError):next_model(dict(model_id=MODELS[0],end_reason='provider_unavailable',stop_trigger='model_http_429'))
        for reason in ('agent_completed','agent_error','budget_exhausted'):
            self.assertEqual(next_model(dict(model_id=MODELS[2],end_reason=reason)),MODELS[0])

    def test_fallback_consumes_next_same_condition_slot_without_extra_slots(self):
        c,i=load(self.root);first=i['runs'][0]
        first['run_id']='failed-run'
        atomic(self.root/'run-index.json',i)
        atomic(self.root/'runs'/first['planned_run']/'attempt/manifest.json',dict(model_id=MODELS[0],end_reason='provider_unavailable',stop_trigger='model_http_503'))
        other=next(r for r in i['runs'] if r['condition']!=first['condition'])
        same=next(r for r in i['runs'][1:] if r['condition']==first['condition'])
        self.assertEqual(slot_config(self.root,c,other)['model_id'],MODELS[0])
        self.assertEqual(slot_config(self.root,c,same)['model_id'],MODELS[1])
        self.assertEqual(len(load(self.root)[1]['runs']),20)

    def test_missing_completion_blocks_next_start(self):
        c,i=load(self.root);i['runs'][0]['run_id']='begun'
        with self.assertRaises(FileNotFoundError):next_slot(self.root,c,i)

    def test_unstarted_gap_cannot_be_skipped(self):
        c,i=load(self.root);i['runs'][1]['run_id']='out-of-order'
        with self.assertRaises(ValueError):next_slot(self.root,c,i)

    def acquisition_fixture(self):
        from test_telemetry_link import fixture
        from preserve import pack
        from gateway_usage import collect
        c,i=load(self.root);row=i['runs'][0]
        run=self.root/'runs'/row['planned_run']/'attempt'
        rid,_=fixture(run,experiment_id=c['experiment_id']);row.update(run_id=rid,status='awaiting_collection')
        m=read(run/'manifest.json');m.update(model_id=MODELS[0],phase='data-acquisition')
        atomic(run/'manifest.json',m);atomic(run/'usage.json',collect(run/'raw-usage'))
        atomic(self.root/'run-index.json',i)
        archive=Path(self.temp.name)/'archive'
        atomic(Path(c['authorization_file']),{'preservation':{'archive':{'linux':str(archive),'windows':str(archive)}}})
        ref=pack(archive,'original-'+rid,{n:run/n for n in ('manifest.json','snapshot.json','frozen','raw-usage','telemetry','usage.json')})
        atomic(run/'preservation.json',ref)
        return c,i,row,run

    def test_monitor_failure_retains_originals_and_allows_next_slot(self):
        from serial_acquisition import collect_run
        from telemetry_link import selected_measurement
        c,i,row,run=self.acquisition_fixture()
        before=(run/'raw-usage/events.jsonl').read_bytes()
        with patch('serial_acquisition.link',side_effect=ValueError('synthetic monitor unavailable')):
            result=collect_run(self.root,c,row,run,{'database_path':str(Path(self.temp.name)/'db')})
        self.assertTrue(result['may_continue'])
        self.assertEqual(next_slot(self.root,c,i)['planned_run'],i['runs'][1]['planned_run'])
        self.assertEqual((run/'raw-usage/events.jsonl').read_bytes(),before)
        self.assertEqual(selected_measurement(run)['total_tokens'],27)
        self.assertEqual(selected_measurement(run)['monitor']['status'],'failed')

    def test_unconfirmed_stop_or_failed_restore_prevents_continuation(self):
        from serial_acquisition import collect_run
        c,i,row,run=self.acquisition_fixture()
        with patch('serial_acquisition.restore',side_effect=OSError('archive unavailable')):
            with self.assertRaises(OSError): collect_run(self.root,c,row,run,{})
        with patch('serial_acquisition.restore',return_value={}),patch('serial_acquisition.link') as link:
            m=read(run/'manifest.json');m['processes_stopped']=False;atomic(run/'manifest.json',m)
            with self.assertRaises(ValueError): collect_run(self.root,c,row,run,{})
            link.assert_not_called()

    def test_completion_requires_final_response_then_turn_end_and_idle(self):
        import json
        from run_copilot import completion_declaration
        encode=lambda events:'\n'.join(json.dumps(e) for e in events)
        events=[{'type':'assistant.turn_start'}, {'type':'assistant.message','data':{'content':'Done.'}},
                {'type':'assistant.turn_end'},{'type':'assistant.idle'}]
        self.assertIsNotNone(completion_declaration(encode(events)))
        self.assertIsNone(completion_declaration(encode(events[:2]+events[3:])))
        self.assertIsNone(completion_declaration(encode(events+[{'type':'assistant.turn_start'}])))
        events[1]['data']['toolRequests']=[{'name':'bash'}]
        self.assertIsNone(completion_declaration(encode(events)))

    def test_503_refusal_is_not_a_missing_successful_usage_record(self):
        import json
        from serial_acquisition import confirmed_503_accounting
        run=Path(self.temp.name)/'accounting';raw=run/'raw-usage';raw.mkdir(parents=True)
        start=dict(event_id='one',run_id='run',request_id='one',model_id=MODELS[0],provider='opencode-go')
        (raw/'started.jsonl').write_text(json.dumps(start)+'\n')
        def outcome(code):
            (raw/'events.jsonl').write_text(json.dumps(dict(start,http_status=code,usage=None))+'\n')
        telemetry=dict(status='readback_verified',adapter_problems=[],model_calls=[])
        outcome(503);self.assertTrue(confirmed_503_accounting(run,telemetry))
        outcome(429);self.assertFalse(confirmed_503_accounting(run,telemetry))
        outcome(200);self.assertFalse(confirmed_503_accounting(run,telemetry))
        outcome(503);(raw/'started.jsonl').write_text(json.dumps(start)+'\n'+json.dumps(dict(start,event_id='lost'))+'\n')
        self.assertFalse(confirmed_503_accounting(run,telemetry))

    def test_unscored_originals_restore_without_quality_fabrication(self):
        from test_telemetry_link import fixture
        from telemetry_link import canonical
        from gateway_usage import collect
        from copilot_batch import export
        from copilot_analysis_archive import preserve_analysis, restore_analysis
        c,i=load(self.root);row=i['runs'][0]
        run=self.root/'runs'/row['planned_run']/'attempt'
        rid,_=fixture(run,experiment_id=c['experiment_id'])
        row.update(run_id=rid,status='awaiting_evaluation')
        m=read(run/'manifest.json');m.update(phase='data-acquisition',model_id=MODELS[1],experiment_version=c['experiment_version']+'-'+MODELS[1],distribution={'condition':row['condition']})
        atomic(run/'manifest.json',m);atomic(self.root/'run-index.json',i)
        atomic(run/'usage.json',dict(usage_complete=True,total_tokens=27,observed_tokens=27))
        from preserve import digest
        atomic(run/'telemetry-link.json',dict(run_id=rid,submission_hash=digest(run/'snapshot.json'),
            native_sha256=digest(run/'telemetry/native.jsonl'),gateway_usage_hash=canonical(collect(run/'raw-usage')),
            usage_complete=True,status='readback_verified',model_calls=[{'tokens':[21,6]}]))
        from telemetry_link import project_measurement
        projection=run/'measurements'/'fixture-processing'
        project_measurement(run,projection)
        atomic(run/'measurement-ref.json',dict(path='measurements/fixture-processing/measurement.json',sha256=digest(projection/'measurement.json')))
        validity=Path(self.temp.name)/'validity.json';atomic(validity,dict(schema_version=1,attempts=[]))
        before=export(self.root,validity,output=Path(self.temp.name)/'before')
        archive=Path(self.temp.name)/'archive'
        ref=preserve_analysis(self.root,validity,archive)
        restored=Path(self.temp.name)/'restored';mapping=restore_analysis(archive,ref,restored)
        after=export(restored/'payload/batch',restored/'payload/validity.json',output=Path(self.temp.name)/'after',restoration_map=mapping)
        self.assertEqual(before,after)
        import csv
        with (Path(self.temp.name)/'after/runs.csv').open(encoding='utf-8-sig') as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),20)
        actual=next(r for r in rows if r['run_id']==rid)
        self.assertEqual(actual['quality_percent'],'')
        self.assertEqual(actual['model_id'],MODELS[1])
        self.assertEqual(actual['total_tokens'],'27')


if __name__=='__main__':unittest.main()

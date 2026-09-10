"""No model calls: actual child processes exercise the 40-slot pipeline."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from copilot_parallel import make_plan,load
from parallel_acquisition import POLICY,MODELS,run_controller,select_model,validate_batch
from telemetry_link import atomic
from preserve import read
from test_parallel_batch import WORKER


@unittest.skipUnless(os.name=='posix','Controller runs on the Linux Docker host')
class Pipeline(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'batch'
        self.script=Path(self.temp.name)/'worker.py';self.script.write_text(WORKER)
        self.validity=Path(self.temp.name)/'validity.json';atomic(self.validity,{'attempts':[]})
        make_plan(self.root,dict(batch_schema=2,phase='data-acquisition',acquisition_policy=POLICY,
            repetitions_per_condition=20,max_parallel=5,synthetic=True,model_id=MODELS[0],
            experiment_version='synthetic-parallel-acquisition'),20260911)
    def command(self,root,c,row,assignment):
        # Start order intentionally differs from completion order.
        return [sys.executable,str(self.script),str(assignment),str(.01*(6-row['execution_order']%5))]
    def collect(self,root,c,row,run):
        time.sleep(.005)
        manifest=read(run/'manifest.json');manifest.update(end_reason='agent_completed',model_id=row['model_id'])
        atomic(run/'manifest.json',manifest)
        return {'may_continue':True,'stop_reason':''}
    def evaluate(self,root,c,row,run):
        time.sleep(.06)
        eid='evaluation-'+row['run_id']
        return {'result':{'evaluation_id':eid},'records':[{'evaluation_id':eid,'run_id':row['run_id']}]}
    def test_forty_balanced_starts_rolling_slots_and_scoring_overlap(self):
        run_controller(self.root,self.command,self.collect,self.evaluate,self.validity)
        _,i=load(self.root)
        self.assertEqual(len({r['run_id'] for r in i['runs']}),40)
        self.assertEqual({r['status'] for r in i['runs']},{'awaiting_review'})
        self.assertEqual(len(read(self.validity)['attempts']),40)
        events=[json.loads(l) for l in (self.root/'pipeline-events.jsonl').read_text().splitlines()]
        occupied=set();scores=set();peak=0;overlap=False;rolling=False
        started=[]
        for e in events:
            if e['event']=='implementation_started':
                occupied.add(e['run_id']);started.append(e['run_id']);peak=max(peak,len(occupied))
                if len(started)>5 and occupied:rolling=True
            if e['event']=='preserved_and_restored':occupied.remove(e['run_id'])
            if e['event']=='evaluation_started':
                scores.add(e['run_id']);overlap|=bool(occupied)
                self.assertLessEqual(len(scores),4 if e['generation_done'] else 1)
            if e['event']=='evaluation_preserved':scores.remove(e['run_id'])
            self.assertLessEqual(len(occupied),5)
        self.assertEqual(peak,5);self.assertTrue(overlap);self.assertTrue(rolling)
        self.assertEqual(started,[r['run_id'] for r in i['runs']])
        self.assertEqual(sum(r['condition']=='anti' for r in i['runs']),20)
    def test_restore_failure_stops_new_starts_but_drains_peers(self):
        def collect(root,c,row,run):
            if row['execution_order']==1:raise OSError('synthetic restore failure')
            return self.collect(root,c,row,run)
        state=run_controller(self.root,self.command,collect,self.evaluate,self.validity)
        _,i=load(self.root)
        self.assertEqual(state['stop_reason'],'collection_or_restoration_failed')
        self.assertLess(sum(bool(r['run_id']) for r in i['runs']),40)
        self.assertTrue(any(r['status']=='awaiting_review' for r in i['runs']))
        self.assertFalse(any(r['status'] in ('running','collecting','evaluating') for r in i['runs']))
    def test_sustained_429_preserves_failed_run_and_stops_new_starts(self):
        def collect(root,c,row,run):
            self.collect(root,c,row,run)
            return {'may_continue':False,'stop_reason':'repeated_http_429'}
        state=run_controller(self.root,self.command,collect,self.evaluate,self.validity)
        _,i=load(self.root)
        self.assertEqual(state['stop_reason'],'repeated_http_429')
        self.assertEqual(sum(bool(r['run_id']) for r in i['runs']),5)
        self.assertEqual(len(read(self.validity)['attempts']),5)
    def test_simultaneous_503_uses_distinct_same_condition_fallback_slots(self):
        def collect(root,c,row,run):
            self.collect(root,c,row,run)
            if row['execution_order']<=5:
                m=read(run/'manifest.json');m.update(end_reason='provider_unavailable',stop_trigger='model_http_503')
                atomic(run/'manifest.json',m)
            return {'may_continue':True,'stop_reason':''}
        run_controller(self.root,self.command,collect,self.evaluate,self.validity)
        _,i=load(self.root);children=[r for r in i['runs'] if r.get('fallback_of')]
        self.assertEqual(len(children),5)
        self.assertEqual(len({r['fallback_of'] for r in children}),5)
        for child in children:
            parent=next(r for r in i['runs'] if r['run_id']==child['fallback_of'])
            self.assertEqual(child['condition'],parent['condition']);self.assertEqual(child['model_id'],MODELS[1])
        self.assertEqual(len(i['runs']),40)
    def test_complete_restart_does_not_repeat_model_or_evaluation(self):
        run_controller(self.root,self.command,self.collect,self.evaluate,self.validity)
        state=read(self.root/'controller.json');state['owner']=dict(pid=99999999,start_ticks='0',boot_id='none')
        atomic(self.root/'controller.json',state)
        def forbidden(*args):self.fail('Completed slot was rerun')
        run_controller(self.root,forbidden,forbidden,forbidden,self.validity,resume=True)
        self.assertEqual(len(read(self.validity)['attempts']),40)
    def test_uncertain_reservation_is_never_reused(self):
        c,i=load(self.root);i['runs'][0].update(run_id='uncertain',status='reserved');atomic(self.root/'run-index.json',i)
        with self.assertRaises(ValueError):run_controller(self.root,self.command,self.collect,self.evaluate,self.validity,resume=True)
        self.assertEqual(load(self.root)[1]['runs'][0]['run_id'],'uncertain')
    def test_bad_budget_and_legacy_policy_are_rejected(self):
        c,i=load(self.root)
        for change in ({'max_parallel':True},{'max_parallel':6},{'repetitions_per_condition':21},{'acquisition_policy':None}):
            with self.assertRaises(ValueError):validate_batch(dict(c,**change),i)

    def test_real_generation_gate_binds_owner_assignment_model_sources_and_budget(self):
        import hashlib,uuid
        from copilot_scope import settings_hash
        from parallel_acquisition import assigned_config,check_generation,SCOPE
        from copilot_parallel import process_identity
        from prepare_workspace import render_contract
        from execution_scope import ROOT
        from preserve import digest
        batch=Path(self.temp.name)/'real-gate'
        c=read(ROOT/'results/acquisition10-20260910/batch/experiment.json')
        c.update(experiment_id=str(uuid.uuid4()),repetitions_per_condition=20,max_parallel=5,
            acquisition_policy=POLICY,authorization_file=str(batch.parent/'scope.json'))
        make_plan(batch,c,20260911);c,i=load(batch)
        row=i['runs'][0];row.update(run_id=str(uuid.uuid4()),model_id=MODELS[0],status='reserved',dispatch_id='gate-test')
        atomic(batch/'run-index.json',i)
        selected=assigned_config(batch,c,row);directory=batch/'runs'/row['planned_run']
        atomic(directory/'execution-config.json',selected)
        atomic(directory/'assignment.json',dict(row,execution_config_sha256=digest(directory/'execution-config.json')))
        proof=dict(policy=POLICY,experiment_id=c['experiment_id'],plan_sha256=i['plan_sha256'],input_hashes=c['input_hashes'],
            checks_passed=True,model_called=False,
            source_hashes={'scripts/parallel_acquisition.py':digest(ROOT/'scripts/parallel_acquisition.py')},
            models={MODELS[0]:dict(settings_sha256=settings_hash(selected),contract_sha256=hashlib.sha256(render_contract(ROOT,selected)).hexdigest())})
        atomic(batch.parent/'generation-proof.json',proof)
        scope=dict(authorized_scope=SCOPE,generation_policy=POLICY,acquisition_root=str(batch),
            allowed_starts=[r['planned_run'] for r in i['runs']],preservation={'generation_readiness':{'test_receipt':True}})
        atomic(Path(c['authorization_file']),scope)
        controller=dict(status='running',owner=process_identity(),dispatch_id='gate-test',
            generation_proof_sha256=digest(batch.parent/'generation-proof.json'),generation_readiness=scope['preservation']['generation_readiness'])
        atomic(batch/'controller.json',controller)
        # restore() returns a receipt locator; verify_receipt() returns its payload.
        from parallel_acquisition import verify_ready
        archive=batch.parent/'archive';payload=archive/'packages/proof/payload';payload.mkdir(parents=True)
        (payload/'proof.json').write_bytes((batch.parent/'generation-proof.json').read_bytes())
        with patch('preserve.verify_receipt',return_value={'reference':{'package_id':'proof'}}), \
                patch('parallel_acquisition.verify_receipt',return_value={'reference':{'package_id':'proof'}}), \
                patch('preservation_gate.archive_root',return_value=archive):
            self.assertEqual(verify_ready(batch,c,i),scope['preservation']['generation_readiness'])
        self.assertEqual(check_generation(selected,scope)['dispatch_id'],'gate-test')
        with self.assertRaises(ValueError):check_generation(dict(selected,model_id=MODELS[1]),scope)
        with self.assertRaises(ValueError):check_generation(selected,dict(scope,allowed_starts=[]))
        for r in i['runs'][1:6]:r.update(run_id=str(uuid.uuid4()),status='reserved')
        atomic(batch/'run-index.json',i)
        with self.assertRaises(ValueError):check_generation(selected,scope)


if __name__=='__main__':unittest.main()

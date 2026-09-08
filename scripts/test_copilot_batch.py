import json
from pathlib import Path
import tempfile
import unittest
from copilot_batch import plan,advance,load,status,lock
from telemetry_link import atomic
from test_telemetry_link import fixture
from preserve import read


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'batch'
        plan(self.root,{'experiment_version':'copilot-test','synthetic':True},123)
        self.calls=[]

    def runner(self,root,c,row,run):
        self.calls.append(row['run_id']);fixture(run,row['run_id'],c['experiment_id'])
        atomic(run/'usage.json',{'usage_complete':True})

    def test_fixed_schedule_and_no_completed_restart(self):
        c,i=load(self.root)
        self.assertEqual(len(i['runs']),40)
        for start in range(0,40,2):self.assertEqual({r['condition'] for r in i['runs'][start:start+2]},{'normal','anti'})
        advance(self.root,self.runner,lambda *a:{'evaluation_id':'fake','valid':True},limit=2)
        first=self.calls[:]
        advance(self.root,self.runner,lambda *a:{'evaluation_id':'fake','valid':True},limit=1)
        self.assertEqual(len(self.calls),3);self.assertEqual(self.calls[:2],first)
        with lock(self.root),self.assertRaises(FileExistsError):advance(self.root,self.runner)

    def test_killed_start_is_never_reset_or_reimplemented(self):
        def fail(*args):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):advance(self.root,fail)
        before=read(self.root/'run-index.json')['runs'][0]['run_id']
        advance(self.root,self.runner)
        self.assertEqual(self.calls,[])
        self.assertEqual(read(self.root/'run-index.json')['runs'][0]['run_id'],before)
        self.assertEqual(status(self.root)['started'],1)

    def test_measurement_and_evaluator_failure_stop_before_second(self):
        def incomplete(root,c,row,run):
            self.runner(root,c,row,run);atomic(run/'usage.json',{'usage_complete':False})
        advance(self.root,incomplete)
        self.assertEqual(status(self.root)['states']['missing'],1)
        self.assertEqual(status(self.root)['started'],1)

    def test_plan_tampering_detected(self):
        c=read(self.root/'experiment.json');c['experiment_version']='changed';atomic(self.root/'experiment.json',c)
        with self.assertRaises(ValueError):load(self.root)

    def test_validation_has_only_two_slots_and_cannot_restart(self):
        root=self.root.parent/'validation'
        plan(root,{'experiment_version':'copilot-validation-test','phase':'copilot-validation','synthetic':True},123)
        self.assertEqual(status(root)['planned'],2)
        self.assertEqual({r['condition'] for r in load(root)[1]['runs']},{'normal','anti'})
        def runner(root,c,row,run):
            self.runner(root,c,row,run)
            manifest=read(run/'manifest.json');manifest['phase']='copilot-validation';atomic(run/'manifest.json',manifest)
        advance(root,runner,lambda *a:{'evaluation_id':'fake','valid':True},limit=1)
        self.assertEqual(status(root)['started'],1)
        advance(root,runner,lambda *a:{'evaluation_id':'fake','valid':True})
        advance(root,runner,lambda *a:{'evaluation_id':'fake','valid':True})
        self.assertEqual(len(self.calls),2)

    def test_validation_rejects_comparison_manifest(self):
        root=self.root.parent/'validation'
        plan(root,{'experiment_version':'copilot-validation-test','phase':'copilot-validation'},123)
        with self.assertRaisesRegex(ValueError,'phase differs'):
            advance(root,self.runner)
        self.assertEqual(status(root)['started'],1)
        advance(root,self.runner)
        self.assertEqual(len(self.calls),1)

    def test_export_failure_stops_before_next_start(self):
        def failed_export(root):
            self.assertEqual(read(root/'run-index.json')['runs'][0]['status'],'completed')
            raise ValueError('export failed')
        with self.assertRaisesRegex(ValueError,'export failed'):
            advance(self.root,self.runner,lambda *a:{'evaluation_id':'fake','valid':True},after_evaluation=failed_export)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(status(self.root)['states']['failed'],1)

    def test_export_directory_cannot_mix_modes(self):
        from copilot_batch import export
        directory=self.root.parent/'export';directory.mkdir()
        atomic(directory/'provenance.json',{'phase':'copilot-validation','experiment_id':load(self.root)[0]['experiment_id']})
        with self.assertRaisesRegex(ValueError,'different phase'):
            export(self.root,Path('unused'),output=directory)

    def test_phase_mixing_rejected_in_analysis(self):
        from aggregate import aggregate
        from collect_runs import collect
        ledger=read(Path(__file__).resolve().parents[1]/'evaluation/requirements-ledger.json')
        run={'run_id':'test','phase':'copilot-validation','condition':'normal'}
        with self.assertRaisesRegex(ValueError,'Invalid phase'):
            aggregate([run],[],ledger)
        with self.assertRaisesRegex(ValueError,'Invalid phase'):
            aggregate([dict(run,phase='comparison')],[],ledger,validation=True)
        directory=self.root.parent/'selected';fixture(directory)
        atomic(directory/'usage.json',{'usage_complete':False,'total_tokens':None})
        manifest=read(directory/'manifest.json');manifest['phase']='copilot-validation';atomic(directory/'manifest.json',manifest)
        registry=self.root.parent/'validity.json';atomic(registry,{'schema_version':1,'attempts':[]})
        with self.assertRaisesRegex(ValueError,'analysis mode'):
            collect([{'run_directory':str(directory),'evaluation_directory':None}],validity_path=registry)

    def test_validation_scope_keeps_preservation_and_consumes_start(self):
        from unittest.mock import patch
        import copilot_scope
        config=read(Path(__file__).resolve().parents[1]/'config/copilot-example.json')
        scope_path=self.root.parent/'scope.json'
        config.update(experiment_id='70075fed-73b9-4fda-8705-221e4df0d157',phase='copilot-validation',
                      model_id='muse-spark-1.3-contributor-free',planned_run='normal-001',condition='normal',
                      authorization_file=str(scope_path),budget={'kind':'wall_clock_seconds','scope':'container','value':3600},
                      environment={'image':'sha256:'+'a'*64})
        scope={'settings_sha256':copilot_scope.settings_hash(config),'allowed_starts':['normal-001'],
               'do_not_start':[],'account_terms_confirmed':True,'exact_model_confirmed':True}
        atomic(scope_path,scope)
        with self.assertRaisesRegex(ValueError,'Preservation'):
            copilot_scope.check(config)
        with patch('preservation_gate.check_restoration') as preservation:
            copilot_scope.check(config)
            self.assertTrue(preservation.called)
            with self.assertRaises(KeyError):copilot_scope.check(dict(config,phase='comparison'))
            copilot_scope.reserve(config,'run-1')
            with self.assertRaisesRegex(ValueError,'consumed'):copilot_scope.check(config)
            copilot_scope.check(config,'run-1')

if __name__=='__main__':unittest.main()

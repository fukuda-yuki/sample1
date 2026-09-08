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

if __name__=='__main__':unittest.main()

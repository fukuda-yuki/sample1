import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from copilot_batch import plan,load,status
from copilot_parallel import dispatch,set_parallel,extend,positive
from telemetry_link import atomic

WORKER = r'''
import json,sys,time,hashlib,os
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text());d=Path(sys.argv[1]).parent;root=Path(a['root'])
(d/'active').write_text(a['run_id'])
if sys.argv[2]=='barrier':
 deadline=time.monotonic()+20
 while len(list((root/'runs').glob('*/active')))<20:
  if time.monotonic()>deadline:raise RuntimeError('20 workers did not overlap')
  time.sleep(.05)
else:time.sleep(float(sys.argv[2]))
r=d/'attempt';(r/'frozen').mkdir(parents=True)
(r/'frozen/marker').write_text(a['run_id'])
snapshot={'marker':hashlib.sha256(a['run_id'].encode()).hexdigest()}
(r/'snapshot.json').write_text(json.dumps(snapshot))
(r/'manifest.json').write_text(json.dumps(dict(run_id=a['run_id'],distribution={'condition':a['condition']},submission_fixed=True,processes_stopped=True)))
(r/'usage.json').write_text(json.dumps({'usage_complete':False}))
result=dict(run_id=a['run_id'],experiment_id=a['experiment_id'],planned_run=a['planned_run'],producer_stopped=True,submission_hash=hashlib.sha256((r/'snapshot.json').read_bytes()).hexdigest())
t=d/'result.tmp';t.write_text(json.dumps(result));t.replace(d/'execution-result.json')
(d/'finished').write_text(str(time.time()))
'''


class Inputs(unittest.TestCase):
    def test_bad_numbers(self):
        for value in (None,True,False,0,-1,1.5,'2'):
            with self.assertRaises(ValueError):positive(value,'N')


@unittest.skipUnless(os.name=='posix','Parallel orchestration runs on the Linux Docker host')
class Parallel(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'batch';self.script=Path(self.temp.name)/'worker.py';self.script.write_text(WORKER)
    def create(self,n=10,k=20):
        plan(self.root,dict(batch_schema=2,repetitions_per_condition=n,max_parallel=k,
             experiment_version='synthetic-parallel',synthetic=True,phase='comparison'),37)
    def command(self,delay):
        return lambda root,c,row,a:[sys.executable,str(self.script),str(a),str(delay)]
    def test_twenty_real_processes_overlap_and_keep_identity(self):
        self.create();dispatch(self.root,self.command('barrier'),k=20)
        c,i=load(self.root)
        self.assertEqual(status(self.root)['started'],20)
        for row in i['runs']:
            self.assertEqual((self.root/'runs'/row['planned_run']/'attempt/frozen/marker').read_text(),row['run_id'])
        dispatch(self.root,self.command(0),recover_only=True)
        self.assertEqual([r['run_id'] for r in load(self.root)[1]['runs']],[r['run_id'] for r in i['runs']])
    def test_live_k_change_and_limit(self):
        self.create(n=10,k=2);errors=[]
        def controls():
            try:
                while len(list((self.root/'runs').glob('*/active')))<2:time.sleep(.02)
                set_parallel(self.root,10)
                while len(list((self.root/'runs').glob('*/active')))<10:time.sleep(.02)
                set_parallel(self.root,2)
            except Exception as e:errors.append(e)
        thread=threading.Thread(target=controls,daemon=True);thread.start()
        dispatch(self.root,self.command(1),limit=12);thread.join(timeout=5)
        self.assertFalse(errors);self.assertFalse(thread.is_alive())
        c,i=load(self.root);d=json.loads((self.root/'dispatches'/f"{i['dispatch_id']}.json").read_text())
        self.assertEqual([x['current'] for x in d['changes']],[10,2]);self.assertEqual(status(self.root)['started'],12)
    def test_extend_keeps_slots_and_refuses_reduction(self):
        self.create(n=3,k=1);before=load(self.root)[1]['runs']
        extend(self.root,10);after=load(self.root)[1]['runs']
        self.assertEqual(after[:6],before);self.assertEqual(len(after),20)
        with self.assertRaises(ValueError):extend(self.root,3)
    def test_uncertain_start_never_reimplemented(self):
        self.create(n=1,k=1);c,i=load(self.root)
        i['runs'][0].update(status='reserved',run_id='00000000-0000-0000-0000-000000000001');atomic(self.root/'run-index.json',i)
        with self.assertRaises(ValueError):dispatch(self.root,self.command(0))
        self.assertEqual(status(self.root)['started'],1)


if __name__=='__main__':unittest.main()

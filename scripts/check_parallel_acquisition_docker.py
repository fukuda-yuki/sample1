"""Five real CLIs with fake providers plus one isolated evaluation surrogate.

There is no external provider, real credential, or scored research submission.
The sixth container checks concurrent DB/maildrop/network separation, not v6
assertion validity. The evaluator itself remains unchanged and hash-pinned.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from preserve import write_new,read,digest
from run_codex import GATEWAY_IMAGE


def main(output,image):
    output.mkdir(parents=True,exist_ok=False)
    eid=str(uuid.uuid4());name='sample1-eval-probe-'+eid;net=name+'-net'
    evaldir=output/'evaluation-surrogate';evaldir.mkdir()
    script=evaldir/'probe.py'
    script.write_text("""import sqlite3,pathlib,json,time,os
p=pathlib.Path('/evidence');db=sqlite3.connect(p/'app.sqlite')
db.execute('CREATE TABLE marker(value TEXT)');db.execute('INSERT INTO marker VALUES(?)',(os.environ['PROBE_ID'],));db.commit()
(p/'maildrop.json').write_text(json.dumps({'owner':os.environ['PROBE_ID']}))
(p/'started.json').write_text(json.dumps({'id':os.environ['PROBE_ID'],'at':time.time()}))
while not (p/'stop').exists():time.sleep(.1)
assert db.execute('SELECT value FROM marker').fetchone()[0]==os.environ['PROBE_ID']
(p/'completed.json').write_text(json.dumps({'at':time.time(),'db_owner_verified':True}))
""")
    def docker(*args):return subprocess.run(['docker',*args],check=True,capture_output=True,text=True,timeout=60)
    def run(i):
        target=output/('native-'+str(i));log=output/('native-'+str(i)+'.log')
        with log.open('w') as stream:
            p=subprocess.run([sys.executable,str(Path(__file__).with_name('check_copilot_native.py')),
                '--image',image,'--output',str(target),'--background-completion'],stdout=stream,stderr=subprocess.STDOUT,timeout=160)
        if p.returncode:raise ValueError('Native fixture failed: '+str(i))
        return read(target/'evidence.json')
    samples=[];outcomes=[]
    try:
        docker('network','create','--internal','--label','sample1.probe_id='+eid,net)
        docker('run','-d','--name',name,'--network',net,'--read-only','--cap-drop','ALL',
            '--user',f'{os.getuid()}:{os.getgid()}','--env','PROBE_ID='+eid,
            '--mount',f'type=bind,source={evaldir.resolve()},target=/evidence',GATEWAY_IMAGE,'python','/evidence/probe.py')
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures=[pool.submit(run,i) for i in range(5)]
            while not all(f.done() for f in futures):
                names=docker('ps','--format','{{.Names}}').stdout.splitlines()
                owned=[]
                for i in range(5):
                    m=output/('native-'+str(i))/'run/manifest.json'
                    if m.exists():
                        try:
                            rid=read(m)['run_id']
                            if 'sample1-'+rid in names:owned.append(rid)
                        except (ValueError,OSError):pass
                samples.append({'at':time.time(),'workers':owned,'evaluation_running':name in names})
                time.sleep(.2)
            outcomes=[f.result() for f in futures]
        assert len({r['run_id'] for r in outcomes})==5
        assert all(r['model_called'] is False and r['file_edit'] and r['continuation'] and r['delegation_tools_absent'] for r in outcomes)
        assert any(len(s['workers'])==5 and s['evaluation_running'] for s in samples), 'Five CLI workers did not overlap with evaluation surrogate'
        (evaldir/'stop').write_text('stop')
        docker('wait',name)
        assert read(evaldir/'completed.json')['db_owner_verified']
        write_new(output/'evidence.json',{'model_called':False,'real_credentials_used':False,
            'real_cli_runs':5,'evaluation_surrogates':1,'v6_assertions_executed':False,
            'five_plus_one_overlap':True,'isolated_run_ids':True,'outcomes':outcomes,'samples':samples,
            'surrogate_db_verified':True,'source_sha256':digest(Path(__file__))})
        print('PASS: five real CLI/fake-provider Runs overlapped an isolated evaluation surrogate; no model called.')
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)
        subprocess.run(['docker','network','rm',net],capture_output=True,timeout=30)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--image',required=True)
    a=p.parse_args();main(a.output,a.image)

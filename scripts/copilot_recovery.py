"""Explicit recovery of owned runtime and preserved outputs; never starts a model."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid
from preserve import read,digest,pack,verify
from telemetry_link import atomic
from copilot_parallel import alive,load


def stop_process(identity):
    if not alive(identity):return
    descriptor=os.pidfd_open(identity['pid'])
    try:
        if not alive(identity):raise ValueError('Worker process identity changed')
        signal.pidfd_send_signal(descriptor,signal.SIGTERM)
        until=time.monotonic()+30
        while alive(identity) and time.monotonic()<until:time.sleep(.2)
        if alive(identity):raise ValueError('Worker did not confirm stop; retain recovery lock')
    finally:os.close(descriptor)


def recover(root):
    from copilot_batch import lock
    from preservation_gate import archive_root
    from run_experiment import snapshot,verify_snapshot
    from run_codex import save_usage
    from run_cleanup import cleanup,confirmed_absent
    with lock(root,name='recovery.lock',recover_stale=True):
        old_lock=root/'batch.lock'
        saved=read(old_lock) if old_lock.exists() else None
        if saved and (not saved.get('owner') or alive(saved['owner'])):
            raise ValueError('Controller ownership/termination unconfirmed')
        c,index=load(root)
        for row in index['runs']:
            if not row['run_id']:continue
            d=root/'runs'/row['planned_run'];run=d/'attempt'
            if row['status'] not in ('running','reserved','recovery_required'):continue
            started=d/'worker-started.json'
            if started.exists():
                worker=read(started)
                if worker.get('run_id')!=row['run_id']:raise ValueError('Recovery worker identity mismatch')
                stop_process(worker.get('owner'))
            if not (run/'manifest.json').exists():
                raise ValueError('Start unknown; retain reservation without reimplementation')
            m=read(run/'manifest.json')
            if m['run_id']!=row['run_id']:raise ValueError('Recovery manifest mismatch')
            before=digest(run/'manifest.json')
            for kind,name in [('container','sample1-'+row['run_id']),('container','sample1-gateway-'+row['run_id']),('network','sample1-private-'+row['run_id'])]:
                state=subprocess.run(['docker',kind,'inspect',name],capture_output=True,text=True,timeout=30)
                if state.returncode:
                    if not confirmed_absent(state,kind,name):raise ValueError('Runtime allocation inaccessible')
                elif json.loads(state.stdout)[0]['Id']!=m.get('runtime_resources',{}).get(name):
                    raise ValueError('Unrecorded or replaced runtime allocation; retain Run')
            for name,identity in m.get('runtime_resources',{}).items():
                if name.startswith('sample1-private-'):continue
                result=subprocess.run(['docker','inspect',identity],capture_output=True,text=True,timeout=30)
                if result.returncode:
                    if confirmed_absent(result,'container',identity):continue
                    raise ValueError('Runtime state inaccessible')
                resource=json.loads(result.stdout)[0]
                if resource['Config'].get('Labels',{}).get('sample1.run_id')!=row['run_id']:
                    raise ValueError('Recovery resource ownership mismatch')
                if resource['State']['Running']:
                    subprocess.run(['docker','stop','--time','5',identity],check=True,capture_output=True,timeout=30)
                if json.loads(subprocess.check_output(['docker','inspect',identity]))[0]['State']['Running']:
                    raise ValueError('Runtime did not stop')
            raw=Path(m['usage_raw_directory'])
            expected=d/'.raw-usage'/row['run_id']
            if raw.resolve()!=expected.resolve():raise ValueError('Recovery raw location mismatch')
            provider_failure=read(raw/'provider-failure.json') if (raw/'provider-failure.json').exists() else None
            if provider_failure and (provider_failure.get('run_id')!=row['run_id']
                    or provider_failure.get('experiment_id')!=c['experiment_id'] or provider_failure.get('http_status')!=503):
                raise ValueError('Provider failure identity/status mismatch')
            if not m.get('submission_fixed'):
                working=run/'working'
                if not working.is_dir() or working.is_symlink() or working.is_junction():
                    raise ValueError('Recovery working directory unavailable')
                if not m.get('processes_stopped') and not m.get('runtime_resources'):
                    raise ValueError('Runtime allocation/stop unconfirmed; retain Run')
                hashes=snapshot(working)
                frozen=run/'frozen'
                if frozen.exists():
                    # Keep the incomplete freeze for forensic inspection.
                    frozen.rename(run/('incomplete-freeze-'+str(uuid.uuid4())))
                frozen.mkdir()
                for relative in hashes:
                    target=frozen/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(working/relative,target)
                atomic(run/'snapshot.json',hashes)
                m.update(processes_stopped=True,submission_fixed=True,status='ended',end_reason='provider_unavailable' if provider_failure else 'operator_aborted')
                if provider_failure:m.update(stop_trigger='model_http_503',provider_failure=provider_failure)
                atomic(run/'manifest.json',m)
            elif provider_failure and m.get('end_reason')!='provider_unavailable':
                m.update(end_reason='provider_unavailable',stop_trigger='model_http_503',provider_failure=provider_failure)
                atomic(run/'manifest.json',m)
            verify_snapshot(run/'frozen',read(run/'snapshot.json'))
            if not (run/'preservation.json').exists() or not (run/'usage.json').exists() or not read(run/'usage.json').get('producer_stopped'):
                save_usage(run,raw,producer_stopped=True,error=None)
            archive=archive_root(read(Path(c['authorization_file'])))
            receipt_path=run/'preservation.json'
            sources={n:run/n for n in ('manifest.json','snapshot.json','frozen','inputs','raw-usage','usage.json','telemetry','management-source','agent.stdout.log','agent.stderr.log') if (run/n).exists()}
            previous_receipt=read(receipt_path) if receipt_path.exists() else None
            reusable=False
            if previous_receipt:
                data=verify(archive,previous_receipt['package_id'],previous_receipt['sha256'])
                from preserve import tree,content_equal
                current={}
                for name,source in sources.items():
                    if source.is_dir():current.update({name+'/'+n:e for n,e in tree(source).items()})
                    else:current[name]={'sha256':digest(source),'bytes':source.stat().st_size}
                reusable=content_equal(current,data['files'])
            if reusable:receipt=previous_receipt
            else:
                receipt=pack(archive,'recovered-'+row['run_id']+'-'+str(uuid.uuid4()),sources,
                    metadata={'kind':'recovered-copilot-run','run_id':row['run_id']},references=[previous_receipt] if previous_receipt else [])
                atomic(receipt_path,receipt)
            cleanup_result={}
            if (raw/'provider-failure.json').exists() and c.get('model_http_503_policy')=='stop_run_and_cleanup':
                cleanup_result=cleanup(run,row['run_id'],archive,receipt)
                atomic(run/'cleanup-result.json',cleanup_result)
            atomic(d/'execution-result.json',dict(run_id=row['run_id'],experiment_id=c['experiment_id'],planned_run=row['planned_run'],
                producer_stopped=True,submission_hash=digest(run/'snapshot.json'),preservation=receipt,
                cleanup_status=cleanup_result.get('status','not_requested')))
            atomic(d/'recovery-history'/f'{uuid.uuid4()}.json',{'previous_manifest_sha256':before,'run_id':row['run_id'],
                'model_called':False,'previous_preservation':previous_receipt,'preservation':receipt})
        if saved:
            if read(old_lock)!=saved:raise ValueError('Controller lock changed during recovery')
            old_lock.rename(root/('recovered-lock-'+str(uuid.uuid4())+'.json'))

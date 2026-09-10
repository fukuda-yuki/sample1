"""Version 2 bounded batches: one controller, isolated subprocesses, serial collection."""
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import time
import uuid
from preserve import read, digest
from telemetry_link import atomic


def positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(name + ' must be a positive integer')
    return value


def process_identity(pid=None):
    pid=pid or os.getpid()
    if os.name!='posix':
        raise ValueError('Parallel controller requires the Linux Docker host')
    try:
        stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'pid':pid,'start_ticks':stat[19],
                'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except FileNotFoundError:
        return None


def alive(identity):
    return bool(identity) and process_identity(identity['pid'])==identity


def make_plan(root,config,seed):
    from copilot_batch import ROOT, status
    n=positive(config.get('repetitions_per_condition'), 'N')
    positive(config.get('max_parallel',1),'K')
    policy=config.get('model_http_503_policy','stop_run_and_cleanup')
    if policy not in ('stop_run','stop_run_and_cleanup'):
        raise ValueError('Invalid 503 policy')
    if config.get('phase')=='copilot-validation' and n!=1:
        raise ValueError('Bounded validation requires one Run per condition')
    root.mkdir(parents=True,exist_ok=False)
    c=dict(config,experiment_id=config.get('experiment_id') or str(uuid.uuid4()),seed=seed,
           batch_schema=2,model_http_503_policy=policy)
    inputs=('normal/spec.md','anti/spec.md','implementation_prompt.md','evaluation/requirements-ledger.json','evaluation/case-manifest.json')
    c['input_hashes']={p:digest(ROOT/p) for p in inputs}
    for p in inputs:
        target=root/'inputs'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/p).read_bytes())
    order=slots(seed,1,n)
    atomic(root/'experiment.json',c)
    atomic(root/'planned-runs.json',{'experiment_id':c['experiment_id'],'order':order,'repetitions_per_condition':n})
    atomic(root/'run-index.json',{'experiment_id':c['experiment_id'],'config_sha256':digest(root/'experiment.json'),
        'plan_sha256':digest(root/'planned-runs.json'),'plan_path':'planned-runs.json','repetitions_per_condition':n,
        'runs':[dict(s,run_id=None,status='not_started',evaluation_id=None) for s in order]})
    for s in order:(root/'runs'/s['planned_run']).mkdir(parents=True)
    return status(root)


def slots(seed,start,end):
    rng=random.Random(seed);result=[]
    for i in range(1,end+1):
        pair=['normal','anti'];rng.shuffle(pair)
        if i<start:continue
        for j,condition in enumerate(pair):
            result.append(dict(planned_run=f'{condition}-{i:03d}',condition=condition,repetition=i,
                               block=i,execution_order=2*(i-1)+j+1))
    return result


def load(root,input_root=None):
    c,index=read(root/'experiment.json'),read(root/'run-index.json')
    if c.get('batch_schema')!=2 or index['config_sha256']!=digest(root/'experiment.json'):
        raise ValueError('Configuration changed')
    plan_path=index['plan_path']
    from preserve import safe_name
    safe_name(plan_path)
    if digest(root/plan_path)!=index['plan_sha256']:raise ValueError('Plan changed')
    plan=read(root/plan_path)
    if plan['experiment_id']!=c['experiment_id'] or index['experiment_id']!=c['experiment_id']:
        raise ValueError('Experiment identity mismatch')
    if len(plan['order'])!=2*index['repetitions_per_condition'] or len(index['runs'])!=len(plan['order']):
        raise ValueError('Plan count mismatch')
    for row,slot in zip(index['runs'],plan['order']):
        if any(row.get(k)!=v for k,v in slot.items()):raise ValueError('Slot mismatch')
    ids=[r['run_id'] for r in index['runs'] if r['run_id']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate Run UUID')
    for p,h in c['input_hashes'].items():
        if digest((input_root or root/'inputs')/p)!=h:raise ValueError('Pinned input changed')
    return c,index


def extend(root,n):
    from copilot_batch import lock,status
    positive(n,'N')
    with lock(root):
        c,index=load(root)
        if c.get('phase') == 'data-acquisition':raise ValueError('Fixed acquisition cannot be extended')
        if c.get('phase')=='copilot-validation':raise ValueError('Validation cannot be extended')
        if any(r['status'] not in ('not_started','completed','failed','missing') for r in index['runs']):
            raise ValueError('Recover all started resources before extending')
        if n<=index['repetitions_per_condition']:raise ValueError('Only increasing N is permitted')
        previous=read(root/index['plan_path']);more=slots(c['seed'],index['repetitions_per_condition']+1,n)
        path='plan-revisions/'+str(uuid.uuid4())+'.json'
        atomic(root/path,dict(experiment_id=c['experiment_id'],order=previous['order']+more,
                             previous_plan_sha256=index['plan_sha256'],repetitions_per_condition=n))
        index.update(plan_path=path,plan_sha256=digest(root/path),repetitions_per_condition=n)
        index['runs'].extend(dict(s,run_id=None,status='not_started',evaluation_id=None) for s in more)
        for s in more:(root/'runs'/s['planned_run']).mkdir(parents=True)
        atomic(root/'run-index.json',index)
    return status(root)


def set_parallel(root,k):
    from copilot_batch import lock
    positive(k,'K')
    with lock(root,name='parallel-control.lock'):
        c,index=load(root);dispatch=read(root/'dispatches'/f"{index['dispatch_id']}.json")
        if c.get('phase') == 'data-acquisition' and k != 1:raise ValueError('Acquisition is strictly serial')
        if dispatch['status']!='running' or not alive(dispatch['owner']):raise ValueError('Dispatch is not running')
        path=root/'parallel-control.json';old=read(path) if path.exists() else {}
        request=dict(schema_version=1,experiment_id=c['experiment_id'],dispatch_id=index['dispatch_id'],
                     revision=old.get('revision',0)+1,request_id=str(uuid.uuid4()),max_parallel=k,requested_at=time.time())
        atomic(path,request);return dict(request,saved=True,applied=False)


def control(root,c,dispatch):
    path=root/'parallel-control.json'
    if not path.exists():return
    try:
        r=read(path);positive(r['max_parallel'],'K')
        if c.get('phase') == 'data-acquisition' and r['max_parallel'] != 1:raise ValueError('Acquisition is strictly serial')
        if r['experiment_id']!=c['experiment_id'] or r['dispatch_id']!=dispatch['dispatch_id'] or type(r['revision']) is not int:
            raise ValueError('Foreign/stale control request')
        if r['revision']<=dispatch.get('applied_revision',0):return
        dispatch['changes'].append(dict(request_id=r['request_id'],revision=r['revision'],
            previous=dispatch['applied_max_parallel'],current=r['max_parallel'],at=time.time()))
        dispatch.update(applied_max_parallel=r['max_parallel'],applied_revision=r['revision'])
    except (ValueError,KeyError,TypeError,OSError) as e:
        dispatch['control_warning']=str(e)


def execution_result(root,c,row):
    directory=root/'runs'/row['planned_run'];path=directory/'execution-result.json'
    if not path.exists():raise ValueError('Execution result not published; recovery required')
    result=read(path);assignment=read(directory/'assignment.json')
    for k,v in [('run_id',row['run_id']),('experiment_id',c['experiment_id']),('planned_run',row['planned_run'])]:
        if result.get(k)!=v or assignment.get(k)!=v:raise ValueError('Execution identity mismatch')
    run=directory/'attempt';m=read(run/'manifest.json')
    if m['run_id']!=row['run_id'] or m['distribution']['condition']!=row['condition']:
        raise ValueError('Manifest/condition mismatch')
    if not m.get('submission_fixed') or not m.get('processes_stopped') or not result.get('producer_stopped'):
        raise ValueError('Stop/freeze/producer not established')
    from run_experiment import verify_snapshot
    verify_snapshot(run/'frozen',read(run/'snapshot.json'))
    if digest(run/'snapshot.json')!=result['submission_hash']:raise ValueError('Submission changed')
    if result.get('cleanup_status')=='failed':raise ValueError('Cleanup requires recovery')
    if not c.get('synthetic'):
        from preservation_gate import archive_root
        from preserve import verify
        receipt=result.get('preservation')
        if not receipt:raise ValueError('Immutable original preservation missing')
        archive=archive_root(read(Path(c['authorization_file'])))
        verify(archive,receipt['package_id'],receipt['sha256'])
        package=read(archive/'packages'/receipt['package_id']/'package.json')
        if package['metadata'].get('run_id')!=row['run_id'] or package['files']['snapshot.json']['sha256']!=result['submission_hash']:
            raise ValueError('Preservation belongs to another Run/submission')
    return result


def dispatch(root,command_factory,collector=None,*,k=None,limit=None,recover_only=False):
    from copilot_batch import lock,status
    if k is not None:positive(k,'K')
    if limit is not None:positive(limit,'limit')
    with lock(root):
        c,index=load(root)
        if c.get('phase') == 'data-acquisition' and not recover_only:
            if k != 1 or limit != 1:raise ValueError('Acquisition requires K=1 and limit=1')
            from serial_acquisition import next_slot
            next_slot(root, c, index)
        # Recover completed workers only. Uncertain starts are never reused.
        for row in index['runs']:
            if row['run_id'] and row['status'] in ('running','reserved','recovery_required'):
                started=root/'runs'/row['planned_run']/'worker-started.json'
                if started.exists() and alive(read(started).get('owner')):
                    raise ValueError('Owned worker is still running; recovery required')
                execution_result(root,c,row);row['status']='awaiting_collection'
        did=str(uuid.uuid4());d=dict(dispatch_id=did,experiment_id=c['experiment_id'],owner=process_identity(),
            status='running',applied_max_parallel=k or index.get('last_max_parallel') or c.get('max_parallel',1),
            initial_limit=limit,changes=[],started_at=time.time(),active_count=0)
        index['dispatch_id']=did;active={};started_count=0;failure=None
        atomic(root/'dispatches'/f'{did}.json',d);atomic(root/'run-index.json',index)
        try:
            while True:
                for slot,(process,log,row) in list(active.items()):
                    if process.poll() is None:continue
                    log.close();del active[slot]
                    try:execution_result(root,c,row);row['status']='awaiting_collection'
                    except (ValueError,OSError,KeyError) as error:
                        row.update(status='recovery_required',failure=str(error));failure=error
                control(root,c,d)
                d['active_count']=len(active);d['draining_to_target']=len(active)>d['applied_max_parallel']
                atomic(root/'dispatches'/f'{did}.json',d);atomic(root/'run-index.json',index)
                if not failure and not recover_only:
                    for row in index['runs']:
                        control(root,c,d)
                        if len(active)>=d['applied_max_parallel'] or (limit is not None and started_count>=limit):break
                        if row['status']!='not_started':continue
                        row.update(run_id=str(uuid.uuid4()),status='reserved',dispatch_id=did,start_max_parallel=d['applied_max_parallel'])
                        directory=root/'runs'/row['planned_run']
                        assignment=dict(row,experiment_id=c['experiment_id'],config_sha256=index['config_sha256'],
                                        plan_sha256=index['plan_sha256'],root=str(root.resolve()),dispatch_id=did)
                        atomic(directory/'assignment.json',assignment);atomic(root/'run-index.json',index)
                        started_count+=1
                        command=command_factory(root,c,row,directory/'assignment.json')
                        log=(directory/'worker.log').open('x')
                        try:process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                                    cwd=str(root.resolve()),start_new_session=True)
                        except BaseException:log.close();row['status']='recovery_required';raise
                        row['status']='running';active[row['planned_run']]=(process,log,row)
                        atomic(root/'run-index.json',index)
                if not active:break
                time.sleep(0.2)
            if failure:raise failure
            if collector:
                for row in index['runs']:
                    if row['status']!='awaiting_collection':continue
                    collector(root,c,row,root/'runs'/row['planned_run']/'attempt')
                    row['status']='awaiting_evaluation';atomic(root/'run-index.json',index)
        finally:
            for process,log,row in active.values():
                process.terminate()
            for process,log,row in active.values():
                try:process.wait(timeout=30)
                except subprocess.TimeoutExpired:row['status']='recovery_required'
                log.close()
            d.update(status='stopped',finished_at=time.time(),new_starts=started_count)
            index['last_max_parallel']=d['applied_max_parallel']
            atomic(root/'dispatches'/f'{did}.json',d);atomic(root/'run-index.json',index)
    return status(root)

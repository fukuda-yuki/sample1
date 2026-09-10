"""Forty authorized starts, five occupied slots, independent pipelined v6 scoring.

Only the controller changes the batch index and shared validity registry. Workers
publish per-Run results. This policy does not loosen the old serial start gates.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from preserve import read, digest, verify_receipt, write_new
from telemetry_link import atomic
from copilot_parallel import load, process_identity, alive, execution_result
from serial_acquisition import MODELS, next_model, collect_run, verify_completion

POLICY = 'parallel-preserve-first-v1'
SCOPE = 'parallel-generation-20-per-condition'
OCCUPIED = {'reserved', 'running', 'awaiting_collection', 'collecting', 'recovery_required'}


def validate_batch(config, index):
    if (config.get('phase') != 'data-acquisition' or config.get('acquisition_policy') != POLICY
            or type(config.get('max_parallel')) is not int or config['max_parallel'] != 5
            or type(index.get('repetitions_per_condition')) is not int
            or index['repetitions_per_condition'] != 20 or len(index['runs']) != 40
            or config.get('repetitions_per_condition') != 20):
        raise ValueError('This acquisition requires exactly 20+20 starts and K=5')
    for condition in ('normal', 'anti'):
        if sum(r['condition'] == condition for r in index['runs']) != 20:
            raise ValueError('Condition budget mismatch')
    if not config.get('synthetic') and (config['model_id'] != MODELS[0]
            or config['budget'] != {'kind':'wall_clock_seconds','scope':'container','value':3600}
            or config['effort'] is not None or config['subagent_policy'] != 'disabled'):
        raise ValueError('Acquisition execution conditions changed')


def assigned_config(root, config, row):
    model = row['model_id']
    if model not in MODELS:
        raise ValueError('Model outside the authorized fallback chain')
    return dict(config, **{k:row[k] for k in ('planned_run','condition','execution_order')},
                model_id=model, wire_api='responses' if model in MODELS[:2] else 'completions',
                experiment_version=config['experiment_version']+'-'+model)


def select_model(index, row):
    consumed = {r.get('fallback_of') for r in index['runs'] if r.get('fallback_of')}
    pending = sorted((r for r in index['runs'] if r['condition'] == row['condition']
        and r.get('collection_sequence') is not None and r.get('stop_trigger') == 'model_http_503'
        and r['run_id'] not in consumed), key=lambda r:r['collection_sequence'])
    if not pending:
        return MODELS[0], None
    parent = pending[0]
    return next_model(parent), parent['run_id']


def check_generation(config, scope, run_id=None):
    from copilot_scope import settings_hash, reservation_path
    from execution_scope import ROOT
    from prepare_workspace import render_contract
    root = Path(scope['acquisition_root'])
    base, index = load(root)
    validate_batch(base, index)
    if scope.get('authorized_scope') != SCOPE or scope.get('generation_policy') != POLICY:
        raise ValueError('Wrong parallel generation authority')
    row = next((r for r in index['runs'] if r['planned_run'] == config.get('planned_run')), None)
    if not row or row['planned_run'] not in scope.get('allowed_starts', []) or row['planned_run'] in scope.get('do_not_start', []):
        raise ValueError('Unapproved acquisition slot')
    expected = assigned_config(root, base, row)
    if (settings_hash(expected) != settings_hash(config) or config['condition'] != row['condition']
            or config.get('input_hashes') != base['input_hashes'] or config.get('acquisition_policy') != POLICY):
        raise ValueError('Assignment settings changed')
    if not row['run_id'] or (run_id is not None and row['run_id'] != run_id):
        raise ValueError('Assignment UUID mismatch')
    if row.get('fallback_of'):
        parent=next((r for r in index['runs'] if r['run_id']==row['fallback_of']),None)
        if (not parent or parent['condition']!=row['condition']
                or parent.get('collection_sequence') is None or next_model(parent)!=row['model_id']):
            raise ValueError('Fallback lacks a preserved same-condition 503 parent')
    elif row['model_id'] != MODELS[0]:
        raise ValueError('Alternative model requires an observed 503 parent')
    if any(not r['run_id'] for r in index['runs'] if r['execution_order'] < row['execution_order']):
        raise ValueError('Start order gap')
    controller = read(root/'controller.json')
    if (controller['status'] != 'running' or not alive(controller['owner'])
            or row.get('dispatch_id') != controller['dispatch_id']
            or sum(r['status'] in OCCUPIED for r in index['runs']) > 5):
        raise ValueError('Live bounded controller required')
    proof_path = root.parent/'generation-proof.json'
    if controller['generation_proof_sha256'] != digest(proof_path):
        raise ValueError('Generation proof changed')
    proof = read(proof_path)
    if (proof['experiment_id'] != base['experiment_id'] or proof['policy'] != POLICY
            or proof['plan_sha256'] != index['plan_sha256']
            or proof['input_hashes'] != base['input_hashes']
            or controller['generation_readiness'] != scope['preservation']['generation_readiness']):
        raise ValueError('Generation proof binding changed')
    model = proof['models'][config['model_id']]
    if (model['settings_sha256'] != settings_hash(config)
            or model['contract_sha256'] != hashlib.sha256(render_contract(ROOT, config)).hexdigest()):
        raise ValueError('Model contract differs from the preserved proof')
    for name, expected_hash in proof['source_hashes'].items():
        if digest(ROOT/name) != expected_hash:
            raise ValueError('Generation source changed: '+name)
    assignment = read(root/'runs'/row['planned_run']/'assignment.json')
    if (assignment['run_id'] != row['run_id'] or assignment['dispatch_id'] != controller['dispatch_id']
            or assignment['execution_config_sha256'] != digest(root/'runs'/row['planned_run']/'execution-config.json')):
        raise ValueError('Worker assignment changed')
    reserved = reservation_path(config)
    if reserved.exists() and (run_id is None or read(reserved)['run_id'] != run_id):
        raise ValueError('Start already consumed')
    return {'scope_sha256':digest(Path(config['authorization_file'])),
            'generation_proof_sha256':digest(proof_path),'dispatch_id':controller['dispatch_id']}


def verify_ready(root, config, index):
    from preservation_gate import archive_root
    from execution_scope import ROOT
    validate_batch(config, index)
    scope = read(Path(config['authorization_file']))
    if scope.get('authorized_scope') != SCOPE or scope.get('generation_policy') != POLICY:
        raise ValueError('Parallel start authority missing')
    receipt = scope['preservation']['generation_readiness']
    verify_receipt(archive_root(scope), receipt)
    package = archive_root(scope)/'packages'/receipt['reference']['package_id']
    proof = read(root.parent/'generation-proof.json')
    if digest(root.parent/'generation-proof.json') != digest(package/'payload/proof.json'):
        raise ValueError('Restored proof differs from the current proof')
    if (proof['experiment_id'] != config['experiment_id'] or proof['policy'] != POLICY
            or proof['plan_sha256'] != index['plan_sha256'] or proof['input_hashes'] != config['input_hashes']
            or proof['checks_passed'] is not True or proof['model_called'] is not False):
        raise ValueError('Unconfirmed parallel readiness')
    for name, value in proof['source_hashes'].items():
        if digest(ROOT/name) != value:raise ValueError('Pinned source changed: '+name)
    return receipt


def run_controller(root, command_factory, collector, evaluator, validity, *, resume=False):
    """Internal test seams never come from a CLI-supplied command or provider URL."""
    from copilot_batch import lock
    c, index = load(root)
    validate_batch(c, index)
    readiness = None if c.get('synthetic') else verify_ready(root, c, index)
    with lock(root, recover_stale=resume):
        prior = read(root/'controller.json') if (root/'controller.json').exists() else None
        if prior and alive(prior['owner']):raise ValueError('Controller is still alive')
        if prior and not resume:raise ValueError('Explicit resume required')
        if prior:write_new(root/'controller-history'/(prior['dispatch_id']+'.json'), prior)
        # Reconcile stopped producers and existing jobs; never reuse an uncertain start.
        for row in index['runs']:
            directory = root/'runs'/row['planned_run']
            if row['status'] in OCCUPIED:
                started = directory/'worker-started.json'
                if started.exists() and alive(read(started).get('owner')):
                    raise ValueError('Owned worker is still active; collect it before resume')
                execution_result(root,c,row)
                row['status'] = 'awaiting_collection'
            elif row['status'] == 'evaluating':
                row['status'] = 'awaiting_evaluation'  # evaluate_run reuses only existing complete output.
            if row.get('collection_sequence') is not None and not c.get('synthetic'):
                from preservation_gate import archive_root
                verify_completion(root,row,archive_root(read(Path(c['authorization_file']))))
        did = str(uuid.uuid4())
        state = dict(dispatch_id=did,experiment_id=c['experiment_id'],owner=process_identity(),status='running',
            generation_readiness=readiness,generation_proof_sha256=None if c.get('synthetic') else digest(root.parent/'generation-proof.json'),
            started_at=time.time(),stop_reason=None,evaluation_paused_for_resources=False,
            implementation_limit=5,evaluation_limit=1,active_count=0,changes=[],applied_max_parallel=5)
        # A previous provider/retention stop needs an explicit recorded resolution.
        if prior and prior.get('stop_reason'):
            resolution = root/'resume-resolution.json'
            if not resolution.exists() or read(resolution).get('prior_dispatch_id') != prior['dispatch_id']:
                state['stop_reason'] = prior['stop_reason']
        index['dispatch_id'] = did
        active, collecting, evaluating = {}, {}, {}
        last_resource_sample = 0
        sequence = max((r.get('collection_sequence',0) for r in index['runs']),default=0)
        def persist():
            state['active_count'] = sum(r['status'] in OCCUPIED for r in index['runs'])
            atomic(root/'run-index.json',index)
            atomic(root/'controller.json',state)
            atomic(root/'dispatches'/(did+'.json'),state)
        def event(kind, row=None, **detail):
            record=dict(at=time.time(),monotonic=time.monotonic(),event=kind,
                        run_id=row['run_id'] if row else None,**detail)
            with (root/'pipeline-events.jsonl').open('a') as stream:stream.write(json.dumps(record)+'\n')
            print(json.dumps(record),flush=True)
        def stop_signal(*_):
            state['stop_reason']='operator_requested_stop';event('stop_new_starts')
        previous_handler=signal.signal(signal.SIGTERM,stop_signal) if __import__('threading').current_thread() is __import__('threading').main_thread() else None
        persist()
        with ThreadPoolExecutor(max_workers=1) as collect_pool, ThreadPoolExecutor(max_workers=4) as eval_pool:
            try:
                while True:
                    if time.monotonic()-last_resource_sample >= 30:
                        last_resource_sample=time.monotonic()
                        memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
                        available=memory['MemAvailable']*1024
                        if available < 2*1024**3 and active:
                            state['evaluation_paused_for_resources']=True
                            state['resource_pause_reason']='available_memory_below_2GiB'
                        event('resource_sample',available_memory_bytes=available,load_average=list(os.getloadavg()),
                              implementation_processes=len(active),evaluations=len(evaluating))
                    for key,(process,log,row) in list(active.items()):
                        if process.poll() is None:continue
                        log.close();del active[key]
                        try:
                            execution_result(root,c,row);row['status']='awaiting_collection';event('implementation_stopped',row)
                        except Exception as error:
                            row.update(status='recovery_required',failure=str(error));state['stop_reason']='stop_or_preservation_unconfirmed'
                            event('recovery_required',row,error_type=type(error).__name__)
                    for future,row in list(collecting.items()):
                        if not future.done():continue
                        del collecting[future]
                        try:
                            result=future.result();sequence+=1
                            manifest=read(root/'runs'/row['planned_run']/'attempt/manifest.json')
                            row.update(status='awaiting_evaluation',collection_sequence=sequence,
                                end_reason=manifest.get('end_reason'),stop_trigger=manifest.get('stop_trigger'))
                            if not result['may_continue']:state['stop_reason']=result['stop_reason']
                            event('preserved_and_restored',row,may_continue=result['may_continue'])
                        except Exception as error:
                            row.update(status='recovery_required',failure=str(error));state['stop_reason']='collection_or_restoration_failed'
                            event('collection_failed',row,error_type=type(error).__name__)
                    for future,row in list(evaluating.items()):
                        if not future.done():continue
                        del evaluating[future]
                        try:
                            outcome=future.result()
                            if outcome.get('error'):
                                row.update(status='evaluation_error',evaluation_failure=outcome)
                                if outcome.get('resource_shortage'):state['evaluation_paused_for_resources']=True
                                event('evaluation_failed',row,error_type=outcome.get('error_type'))
                            else:
                                registry=read(validity)
                                for entry in outcome['records']:
                                    old=next((r for r in registry['attempts'] if r['evaluation_id']==entry['evaluation_id']),None)
                                    if old is not None and old!=entry:raise ValueError('Conflicting evaluation registry entry')
                                    if old is None:registry['attempts'].append(entry)
                                atomic(validity,registry)
                                row.update(status='awaiting_review',evaluation_id=outcome['result']['evaluation_id'])
                                event('evaluation_preserved',row,evaluation_id=row['evaluation_id'])
                        except Exception as error:
                            row.update(status='evaluation_error',evaluation_failure={'error_type':type(error).__name__,'error':str(error)})
                            event('evaluation_failed',row,error_type=type(error).__name__)
                    persist()
                    # Restore/measurement is one shared collector; it does not wait for scoring.
                    if not collecting:
                        row=next((r for r in index['runs'] if r['status']=='awaiting_collection'),None)
                        if row:
                            row['status']='collecting';persist()
                            collecting[collect_pool.submit(collector,root,c,dict(row),root/'runs'/row['planned_run']/'attempt')]=row
                    # Detect sustained throttling while producers are still alive.
                    if not c.get('synthetic'):
                        for _,_,row in active.values():
                            raw=root/'runs'/row['planned_run']/'.raw-usage'/row['run_id']/'events.jsonl'
                            if raw.exists():
                                lines=raw.read_text().splitlines();codes=[]
                                for line in lines:
                                    try:codes.append(json.loads(line).get('http_status'))
                                    except json.JSONDecodeError:pass  # Producer may be appending its last line.
                                if codes.count(429)>=2:state['stop_reason']='repeated_http_429'
                    if not state['stop_reason']:
                        while sum(r['status'] in OCCUPIED for r in index['runs'])<5:
                            row=next((r for r in index['runs'] if r['status']=='not_started'),None)
                            if row is None:break
                            model,parent=select_model(index,row)
                            row.update(run_id=str(uuid.uuid4()),status='reserved',dispatch_id=did,
                                start_max_parallel=5,model_id=model,fallback_of=parent,reserved_at=time.time())
                            directory=root/'runs'/row['planned_run']
                            atomic(directory/'execution-config.json',assigned_config(root,c,row))
                            assignment=dict(row,experiment_id=c['experiment_id'],root=str(root.resolve()),
                                config_sha256=index['config_sha256'],plan_sha256=index['plan_sha256'],
                                execution_config_sha256=digest(directory/'execution-config.json'))
                            write_new(directory/'assignment.json',assignment);persist()
                            try:
                                command=command_factory(root,c,row,directory/'assignment.json')
                                log=(directory/'worker.log').open('x')
                                process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                    cwd=str(root.resolve()),start_new_session=True)
                                row['status']='running';active[row['planned_run']]=(process,log,row)
                                event('implementation_started',row,model_id=model,fallback_of=parent,
                                    occupied=sum(r['status'] in OCCUPIED for r in index['runs']))
                                persist()
                            except Exception as error:
                                if 'log' in locals() and not log.closed:log.close()
                                row.update(status='recovery_required',failure=str(error));state['stop_reason']='start_failed';break
                    generation_done=not active and not collecting and not any(r['status']=='awaiting_collection' for r in index['runs']) and (
                        state['stop_reason'] is not None or not any(r['status']=='not_started' for r in index['runs']))
                    eval_limit=4 if generation_done else (0 if state['evaluation_paused_for_resources'] else 1)
                    state['evaluation_limit']=eval_limit
                    if generation_done and not state.get('generation_ended_at'):
                        state['generation_ended_at']=time.time();event('generation_ended',started=sum(bool(r['run_id']) for r in index['runs']))
                    if evaluator:
                        while len(evaluating)<eval_limit:
                            row=next((r for r in index['runs'] if r['status']=='awaiting_evaluation'),None)
                            if row is None:break
                            row['status']='evaluating';persist();event('evaluation_started',row,generation_done=generation_done)
                            evaluating[eval_pool.submit(evaluator,root,c,dict(row),root/'runs'/row['planned_run']/'attempt')]=row
                    persist()
                    if generation_done and not evaluating:break
                    time.sleep(.2 if c.get('synthetic') else 2)
                state.update(status='stopped',finished_at=time.time());persist();event('controller_finished',stop_reason=state['stop_reason'])
            finally:
                if previous_handler is not None:signal.signal(signal.SIGTERM,previous_handler)
                if active:
                    state.update(status='interrupted',stop_reason=state['stop_reason'] or 'controller_interrupted');persist()
                    # The worker's SIGTERM path freezes/preserves its owned container.
                    for process,log,row in active.values():process.terminate()
                    for process,log,row in active.values():
                        try:process.wait(timeout=45)
                        except subprocess.TimeoutExpired:row['status']='recovery_required'
                        log.close()
                    persist()
        return state


def real_evaluator(private, image, registry_root):
    def evaluate(root,c,row,run):
        from copilot_batch import evaluate_run
        from preserve import pack,restore
        from preservation_gate import archive_root
        registry=registry_root/'per-run'/(row['run_id']+'.json')
        if not registry.exists():write_new(registry,{'schema_version':1,'attempts':[]})
        try:
            result=evaluate_run(root,c,row,run,private,image,registry)
            return {'result':result,'records':read(registry)['attempts']}
        except Exception as error:
            result={'error_type':type(error).__name__,'error':str(error),
                'resource_shortage':any(s in str(error).lower() for s in ('out of memory','cannot allocate memory','no space left'))}
            job=run.parent/'evaluation-jobs/active.json'
            if job.exists():
                assignment=read(job);result['evaluation_id']=assignment['evaluation_id']
                partial=private/'evaluations'/assignment['evaluation_id']
                if partial.exists():
                    archive=archive_root(read(Path(c['authorization_file'])))
                    ref=pack(archive,'partial-evaluation-'+str(uuid.uuid4()),{'evaluation':partial,'assignment.json':job},
                        metadata={'kind':'partial-evaluation','run_id':row['run_id']})
                    result.update(preservation=ref,restoration=restore(archive,ref,run.parent/('restored-'+ref['package_id'])))
            atomic(run.parent/'evaluation-error.json',result)
            return result
    return evaluate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('--secret-file',type=Path,required=True)
    p.add_argument('--locator',type=Path,required=True);p.add_argument('--private-root',type=Path,required=True)
    p.add_argument('--evaluator-image',required=True);p.add_argument('--validity',type=Path,required=True)
    p.add_argument('--execute-real-model',action='store_true');p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if not a.execute_real_model:p.error('Explicit real-model opt-in required')
    root=a.root.resolve();locator=read(a.locator)
    def command(root,c,row,assignment):
        if c.get('synthetic'):raise ValueError('Synthetic policy cannot use the real CLI')
        check_generation(assigned_config(root,c,row),read(Path(c['authorization_file'])))
        return [sys.executable,str(Path(__file__).with_name('copilot_batch_worker.py')),str(assignment),str(a.secret_file.resolve())]
    run_controller(root,command,lambda r,c,s,d:collect_run(r,c,s,d,locator),
        real_evaluator(a.private_root.resolve(),a.evaluator_image,a.validity.parent),a.validity.resolve(),resume=a.resume)


if __name__=='__main__':main()

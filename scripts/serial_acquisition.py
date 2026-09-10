"""User-authorized 10+10 generation, one start per dispatch, scoring deferred.

This phase has its own restored generation proof. It does not promote historical
evaluation readiness or claim that a synthetic provider is a real model.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from preserve import read, digest, verify_receipt, restore, ensure_package, write_new
from telemetry_link import atomic, link
import sqlite3
import uuid

MODELS = ('muse-spark-1.2-contributor', 'muse-spark-1.3-contributor', 'omen-alpha', 'mimo-v2.5')
CHECKS = {'contract_isolation', 'native_protocol_usage', 'stop_recovery', 'monitor', 'runtime_restoration', 'serial_budget'}


def next_model(previous):
    if not previous or previous['end_reason'] != 'provider_unavailable':
        return MODELS[0]
    if previous.get('stop_trigger') != 'model_http_503':
        raise ValueError('Fallback requires an observed upstream 503')
    index = MODELS.index(previous['model_id']) + 1
    if index == len(MODELS):
        raise ValueError('503 fallback candidates exhausted')
    return MODELS[index]


def slot_config(root, config, row):
    from copilot_parallel import load
    _, index = load(root)
    previous = [r for r in index['runs'] if r['condition'] == row['condition']
                and r['execution_order'] < row['execution_order'] and r['run_id']]
    manifest = read(root/'runs'/previous[-1]['planned_run']/'attempt/manifest.json') if previous else None
    model = next_model(manifest)
    c = dict(config, **{k: row[k] for k in ('planned_run', 'condition', 'execution_order')})
    c.update(model_id=model, wire_api='responses' if model in MODELS[:2] else 'completions',
             experiment_version=config['experiment_version']+'-'+model)
    return c


def verify_completion(root, row, archive):
    run = root/'runs'/row['planned_run']/'attempt'
    completion = read(run.parent/'acquisition-completion.json')
    if completion['run_id'] != row['run_id'] or completion['manifest_sha256'] != digest(run/'manifest.json'):
        raise ValueError('Prior completion identity changed')
    for key in ('original_restoration', 'linked_restoration'):
        verify_receipt(archive, completion[key])
    for name, expected in completion['hashes'].items():
        if digest(run/name) != expected:raise ValueError('Prior acquisition evidence changed')
    from run_experiment import verify_snapshot
    verify_snapshot(run/'frozen', read(run/'snapshot.json'))
    revision = run.parent/'acquisition-continuation.json'
    if revision.exists():
        continuation = read(revision)
        if continuation['prior_completion_sha256'] != digest(run.parent/'acquisition-completion.json'):
            raise ValueError('Continuation source changed')
        if continuation['run_id'] != row['run_id'] or continuation['policy'] != 'preserve-first-v2':
            raise ValueError('Wrong continuation decision')
        verify_receipt(archive, continuation['restoration'])
        if continuation['may_continue'] and completion['stop_reason'] == 'incomplete_usage_or_monitor': return
    if not completion['may_continue']:
        raise ValueError('Prior Run requires stop: '+completion['stop_reason'])


def next_slot(root, config, index):
    from preservation_gate import archive_root
    if config.get('max_parallel') != 1 or index['repetitions_per_condition'] != 10 or len(index['runs']) != 20:
        raise ValueError('Acquisition requires exactly 10+10 and K=1')
    archive = archive_root(read(Path(config['authorization_file'])))
    for condition in ('normal', 'anti'):
        if sum(r['condition'] == condition for r in index['runs']) != 10:
            raise ValueError('Condition budget mismatch')
    first = None
    for row in index['runs']:
        if row['run_id']:
            if first:raise ValueError('Acquisition starts must follow the frozen order')
            verify_completion(root, row, archive)
        elif first is None:first = row
    return first


def check_generation(config, scope, run_id):
    from copilot_scope import settings_hash, reservation_path
    from copilot_parallel import load
    from preservation_gate import archive_root
    from execution_scope import ROOT
    from prepare_workspace import render_contract
    root = Path(scope['acquisition_root'])
    base, index = load(root)
    if base['experiment_id'] != config['experiment_id'] or scope.get('authorized_scope') != 'serial-generation-10-per-condition':
        raise ValueError('Wrong generation authorization')
    row = next((r for r in index['runs'] if r['planned_run'] == config['planned_run']), None)
    if not row or config['planned_run'] not in scope.get('allowed_starts', []):
        raise ValueError('Unapproved acquisition slot')
    expected = slot_config(root, base, row)
    if settings_hash(expected) != settings_hash(config) or config['condition'] != row['condition']:
        raise ValueError('Unapproved acquisition model/condition/settings')
    archive = archive_root(scope)
    for before in index['runs']:
        if before['planned_run'] == row['planned_run']:break
        if not before['run_id']:raise ValueError('Prior slot has not started')
        verify_completion(root, before, archive)
    if base.get('max_parallel') != 1 or len(index['runs']) != 20 or index['repetitions_per_condition'] != 10:
        raise ValueError('Acquisition budget changed')
    if any(r['run_id'] for r in index['runs'] if r['execution_order'] > row['execution_order']):
        raise ValueError('Out of order start')
    if row['run_id'] and run_id is not None and row['run_id'] != run_id:
        raise ValueError('Assignment UUID mismatch')
    receipt = verify_receipt(archive, scope['preservation']['generation_readiness'])
    package = archive/'packages'/receipt['reference']['package_id']
    if read(package/'package.json')['metadata'].get('kind') != 'generation-readiness':
        raise ValueError('Wrong generation proof kind')
    proof = read(package/'payload/proof.json')
    if proof.get('schema_version') != 1 or proof['experiment_id'] != config['experiment_id']:
        raise ValueError('Generation proof binding mismatch')
    binding = proof['models'][config['model_id']]
    if binding['settings_sha256'] != settings_hash(config) or binding['contract_sha256'] != hashlib.sha256(render_contract(ROOT, config)).hexdigest():
        raise ValueError('Generation settings/contract changed')
    if proof['input_hashes'] != config['input_hashes'] or proof['plan_sha256'] != index['plan_sha256']:
        raise ValueError('Generation input/plan changed')
    if set(proof['checks']) != CHECKS:raise ValueError('Generation evidence inventory incomplete')
    for check in proof['checks'].values():
        if check.get('passed') is not True or not check.get('evidence'):raise ValueError('Generation check unconfirmed')
        for ref in check['evidence']:
            if digest(package/'payload'/ref['path']) != ref['sha256']:raise ValueError('Generation evidence changed')
    required = {'scripts/'+n for n in ('serial_acquisition.py','copilot_scope.py','copilot_parallel.py','copilot_batch_worker.py','run_copilot.py','run_experiment.py','model_gateway.py','prepare_workspace.py','telemetry_link.py')}
    if not required.issubset(proof['source_hashes']):raise ValueError('Generation source closure missing')
    for name, expected_hash in proof['source_hashes'].items():
        if digest(ROOT/name) != expected_hash:raise ValueError('Generation source changed: '+name)
    reserved = reservation_path(config)
    if reserved.exists() and (run_id is None or read(reserved)['run_id'] != run_id):
        raise ValueError('Start already consumed')
    return {'scope_sha256':digest(Path(config['authorization_file'])), 'generation_proof':receipt['reference']}


def collect_run(root, config, row, run, locator):
    from preservation_gate import archive_root
    archive = archive_root(read(Path(config['authorization_file'])))
    original = read(run/'preservation.json')
    original_restoration = restore(archive, original, run.parent/'restored-original', resume=True)
    manifest = read(run/'manifest.json')
    if not manifest.get('processes_stopped') or not manifest.get('submission_fixed'):
        raise ValueError('Run stop or fixed submission unconfirmed')
    from run_experiment import verify_snapshot
    verify_snapshot(run/'frozen', read(run/'snapshot.json'))
    try:
        link(run, locator, ingest=True, initialize=not Path(locator['database_path']).exists())
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as error:
        # The original is already independently preserved and restored. Persist
        # postprocessing failure; it is not a new-generation failure.
        if not (run/'telemetry-link.json').exists():
            atomic(run/'telemetry-link.json', dict(run_id=row['run_id'],status='failed',error_type=type(error).__name__))
    from telemetry_link import project_measurement
    processing = run/'measurements'/str(uuid.uuid4())
    project_measurement(run, processing)
    atomic(run/'measurement-ref.json', dict(path=str((processing/'measurement.json').relative_to(run)),sha256=digest(processing/'measurement.json')))
    names = ('manifest.json','snapshot.json','frozen','telemetry','telemetry-link.json','raw-usage','usage.json','measurements','measurement-ref.json')
    linked = ensure_package(archive, 'linked-'+row['run_id'], {n:run/n for n in names},
                            metadata={'kind':'copilot-linked-run','run_id':row['run_id']})
    atomic(run/'linked-preservation.json', linked)
    linked_restoration = restore(archive, linked, run.parent/'restored-linked', resume=True)
    atomic(run/'linked-restoration.json', linked_restoration)
    m, usage, telemetry = read(run/'manifest.json'), read(run/'usage.json'), read(run/'telemetry-link.json')
    reason = ''
    if m['end_reason'] in ('environment_failure','operator_aborted'):reason = m['end_reason']
    if m['end_reason'] == 'provider_unavailable':
        # An explicit HTTP refusal may have no provider usage. Keep totals null,
        # but distinguish that refusal from lost records or a successful response
        # that failed reconciliation. Only the former permits the approved fallback.
        if confirmed_503_accounting(run, telemetry) and reason == 'incomplete_usage_or_monitor':reason = ''
        try:next_model(m)
        except ValueError:reason = 'fallback_exhausted'
    raw = run/'raw-usage/events.jsonl'
    if raw.exists():
        events = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
        if sum(e.get('http_status') == 429 for e in events) >= 2:reason = 'repeated_http_429'
    result = dict(run_id=row['run_id'],manifest_sha256=digest(run/'manifest.json'),
                  original_restoration=original_restoration,linked_restoration=linked_restoration,
                  hashes={n:digest(run/n) for n in ('snapshot.json','usage.json','telemetry-link.json')},
                  may_continue=not reason,stop_reason=reason,model_id=m['model_id'],end_reason=m['end_reason'],
                  acquisition_policy='preserve-first-v2', measurement=read(run/'measurement-ref.json'))
    atomic(run.parent/'acquisition-completion.json', result)
    return result


def confirmed_503_accounting(run, telemetry):
    if telemetry.get('status') != 'readback_verified' or telemetry.get('adapter_problems'):return False
    try:
        raw=run/'raw-usage'
        starts=[json.loads(l) for l in (raw/'started.jsonl').read_text().splitlines() if l.strip()]
        ends=[json.loads(l) for l in (raw/'events.jsonl').read_text().splitlines() if l.strip()]
        if not starts or len(starts)!=len(ends):return False
        by_id={e['event_id']:e for e in ends}
        if len(by_id)!=len(ends) or set(by_id)!={e['event_id'] for e in starts}:return False
        for start in starts:
            if any(start.get(k)!=by_id[start['event_id']].get(k) for k in ('run_id','request_id','model_id','provider')):return False
        if not any(e.get('http_status')==503 for e in ends):return False
        successful=[e for e in ends if e.get('http_status')==200]
        refused=[e for e in ends if e.get('http_status')==503 or e.get('status') in ('local_blocked_after_503','local_cancelled_before_send_after_503')]
        if len(successful)+len(refused)!=len(ends):return False
        calls={e['request_id']:e for e in telemetry.get('model_calls',[])}
        if set(calls)!={e['request_id'] for e in successful}:return False
        return all(tuple(calls[e['request_id']]['tokens']) == ((e.get('usage') or {}).get('input_tokens'),(e.get('usage') or {}).get('output_tokens')) for e in successful)
    except (OSError,ValueError,KeyError,TypeError):return False


def run_all(root, locator, secret):
    from copilot_batch import lock
    from copilot_parallel import load, dispatch
    with lock(root, name='acquisition.lock'):
        while True:
            config, index = load(root)
            row = next_slot(root, config, index)
            if row is None:return
            selected = slot_config(root, config, row)
            check_generation(selected, read(Path(config['authorization_file'])), None)
            def command(r,c,s,assignment):
                return [sys.executable,str(Path(__file__).with_name('copilot_batch_worker.py')),str(assignment),str(secret)]
            dispatch(root, command, lambda r,c,s,p:collect_run(r,c,s,p,locator), k=1, limit=1)
            print(json.dumps({'finished_slot':row['planned_run']}), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--locator',type=Path,required=True)
    p.add_argument('--secret-file',type=Path,required=True);p.add_argument('--execute-real-model',action='store_true')
    args=p.parse_args()
    if not args.execute_real_model:p.error('Explicit real-model opt-in required')
    try:run_all(args.root.resolve(),read(args.locator),args.secret_file.resolve())
    except (ValueError,OSError,KeyError,subprocess.SubprocessError) as error:
        atomic(args.root/'acquisition-stop.json',{'error_type':type(error).__name__,'reason':str(error)})
        raise

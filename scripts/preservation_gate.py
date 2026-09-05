"""Fail-closed preservation prerequisites and single-use pilot starts."""
import os
from pathlib import Path
import sys
from preserve import digest, read, verify, verify_receipt, write_new


def archive_root(scope):
    paths = scope['preservation']['archive']
    return Path(paths['windows' if os.name == 'nt' else 'linux'])


def check(scope, config, root, run_id=None):
    settings = scope.get('preservation')
    if not settings:
        raise ValueError('Preservation prerequisites required')
    if (root / 'config/experiment.json').exists():
        fixed = read(root / 'config/experiment.json')
        for key in ('model_id', 'effort', 'agent_version', 'tool_versions', 'subagent_policy', 'budget'):
            if config.get(key) != fixed[key]:
                raise ValueError('Unapproved execution setting: ' + key)
        for key, value in fixed['environment'].items():
            if config.get('environment', {}).get(key) != value:
                raise ValueError('Unapproved environment setting: ' + key)
        if config.get('batch_id') != scope['batch_id']:
            raise ValueError('Wrong management batch')
    archive = archive_root(scope)
    gate = settings.get('gate')
    if not gate:
        raise ValueError('Restore experiment has not passed')
    cache = {}
    evidence = verify(archive, gate['package_id'], gate['sha256'], cache=cache)
    proof = read(archive / 'packages' / gate['package_id'] / 'payload/proof.json')
    required = {'hashes_match', 'usage_recomputed', 'normal_exit', 'timeout_exit',
                'abnormal_exit', 'normal_fixture', 'threshold_mutation',
                'empty_daemon_restore', 'source_unavailable', 'evaluation_restored'}
    if proof.get('model_called') is not False or set(proof.get('checks', {})) != required or not all(
            value is True for value in proof['checks'].values()):
        raise ValueError('Incomplete restoration experiment')
    if evidence['metadata'].get('kind') != 'restoration-proof':
        raise ValueError('Wrong preservation proof kind')
    for receipt in proof['receipts']:
        verify_receipt(archive, receipt, cache)
    if proof['common'] != settings['common']:
        raise ValueError('Different fixed common package')
    for relative, expected in proof['source_hashes'].items():
        if digest(root / relative) != expected:
            raise ValueError('Management/input version changed: ' + relative)
    reservation = archive / 'starts' / scope['batch_id'] / (config['planned_run'] + '.json')
    if reservation.exists() and (run_id is None or read(reservation)['run_id'] != run_id):
        raise ValueError('Planned Run already consumed; no automatic retry')
    order = read(root / scope['planned_manifest'])['order']
    position = next(i for i, item in enumerate(order) if item['planned_run'] == config['planned_run'])
    for previous in order[:position]:
        completion = read(archive / 'completed' / scope['batch_id'] / (previous['planned_run'] + '.json'))
        start = read(archive / 'starts' / scope['batch_id'] / (previous['planned_run'] + '.json'))
        if completion['run_id'] != start['run_id']:
            raise ValueError('Previous Run identity mismatch')
        for key in ('run_receipt', 'evaluation_receipt'):
            verify_receipt(archive, completion[key], cache)
        run_ref = read(archive / completion['run_receipt']['path'])['reference']
        eval_ref = read(archive / completion['evaluation_receipt']['path'])['reference']
        run_data = verify(archive, run_ref['package_id'], run_ref['sha256'], cache=cache)
        if run_data['metadata'].get('missing'):
            raise ValueError('Previous Run originals incomplete')
        run_root = archive / 'packages' / run_ref['package_id'] / 'payload'
        eval_root = archive / 'packages' / eval_ref['package_id'] / 'payload'
        if read(run_root / 'manifest.json')['run_id'] != start['run_id']:
            raise ValueError('Wrong previous Run archived')
        sys.path.insert(0, str(root / 'analysis'))
        from collect_runs import collect
        runs, _ = collect([{'run_directory': str(run_root),
                           'evaluation_directory': str(eval_root / completion['evaluation_directory'])}],
                          eval_root / completion['evaluation_directory'] / 'evaluator-snapshot/requirements-ledger.json',
                          validity_path=eval_root / 'evaluation-validity.json')
        if not runs[0]['usage_complete'] or runs[0]['evaluation_validity'] != 'valid':
            raise ValueError('Previous Run measurement/evaluation not valid')
    return archive


def reserve(scope, config, root, run_id):
    archive = check(scope, config, root)
    write_new(archive / 'starts' / scope['batch_id'] / (config['planned_run'] + '.json'),
              {'run_id': run_id, 'planned_run': config['planned_run'], 'batch_id': scope['batch_id']})


def preserve_finished(scope, output):
    from preserve import pack_run, restore
    archive = archive_root(scope)
    reference = pack_run(archive, output, [scope['preservation']['common']])
    destination = Path(output).parent / 'restored' / reference['package_id']
    receipt = restore(archive, reference, destination)
    write_new(Path(output) / 'preservation.json',
              {'independently_stored': True, 'restore_verified': True,
               'reference': reference, 'receipt': receipt})
    return destination

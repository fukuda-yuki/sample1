"""Separate, researcher-owned Copilot starts; old pilot reservations stay untouched."""
import hashlib
import json
from pathlib import Path
from preserve import read, write_new


FIXED = ('agent', 'provider', 'base_url', 'wire_api', 'model_id', 'agent_version',
         'experiment_version', 'experiment_id', 'budget', 'subagent_policy', 'environment', 'effort')


def settings_hash(config):
    values={k: config[k] for k in FIXED}
    if config.get('batch_schema')==2:
        values.update({k:config.get(k) for k in ('batch_schema','contract_version','model_http_503_policy')})
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def reservation_path(config):
    base=Path(config['authorization_file']).resolve().parent/'starts'
    if config.get('batch_schema')==2:base=base/config['experiment_id']
    return base/(config['planned_run']+'.json')


COMPATIBLE = ('agent', 'provider', 'base_url', 'wire_api', 'model_id', 'agent_version',
              'budget', 'subagent_policy', 'environment', 'effort', 'tool_versions',
              'input_hashes', 'score_version', 'evaluator_files')
INPUTS = ('normal/spec.md', 'anti/spec.md', 'implementation_prompt.md',
          'evaluation/requirements-ledger.json', 'evaluation/case-manifest.json')


def acceptance_conditions(config):
    """Versioned execution contract, distinct from experiment start authorization."""
    from run_copilot import validate_config
    validate_config(config)
    if any(k not in config for k in COMPATIBLE):
        raise ValueError('Acceptance conditions missing')
    if (not config['score_version'] or not config['evaluator_files']
            or any(not config['input_hashes'].get(k) for k in INPUTS)):
        raise ValueError('Acceptance input/evaluator pins missing')
    result = {'schema_version': 1, **{k: config[k] for k in COMPATIBLE}}
    if config.get('batch_schema') == 2:
        result.update(schema_version=2, batch_schema=2,
                      contract_version=config.get('contract_version'),
                      model_http_503_policy=config.get('model_http_503_policy'))
    return result


def experiment_identity(config):
    return {k: config[k] for k in ('experiment_id', 'experiment_version', 'phase')}


def check_acceptance(config, reference, base):
    """Read hash-pinned researcher evidence; never register or promote fixtures."""
    target = experiment_identity(config)
    if reference.get('target_experiment') != target or target['phase'] != 'comparison':
        raise ValueError('Acceptance target experiment mismatch')
    path = base / reference['path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Live acceptance hash mismatch')
    evidence = read(path)
    source = evidence.get('source_config', {})
    if (evidence.get('schema_version') != 1 or source.get('phase') != 'copilot-validation'
            or evidence.get('kind') != 'real-copilot-muse' or source.get('synthetic')
            or evidence.get('synthetic') is not False or config.get('synthetic')
            or not all(evidence.get(k) is True for k in
                       ('file_edit', 'tool_execution', 'model_continuation', 'usage_reconciled',
                        'monitor_readback', 'independent_evaluation', 'preservation_verified'))):
        raise ValueError('Same-path real acceptance is missing')
    if (evidence.get('source_experiment') != experiment_identity(source)
            or evidence.get('settings_sha256') != settings_hash(source)):
        raise ValueError('Acceptance source binding mismatch')
    if acceptance_conditions(source) != acceptance_conditions(config):
        raise ValueError('Acceptance execution conditions mismatch')
    return {'source_experiment': experiment_identity(source), 'target_experiment': target,
            'evidence_sha256': reference['sha256']}


def check(config, run_id=None):
    from run_copilot import validate_config
    validate_config(config)
    path = Path(config['authorization_file']).resolve()
    scope = read(path)
    if scope.get('settings_sha256') != settings_hash(config):
        raise ValueError('Copilot authorization settings mismatch')
    slot = config['planned_run']
    if slot not in scope.get('allowed_starts', []) or slot in scope.get('do_not_start', []):
        raise ValueError('No explicit Copilot start authorization')
    if not all(scope.get(k) is True for k in ('account_terms_confirmed', 'exact_model_confirmed')):
        raise ValueError('Exact model availability and free/data terms are unconfirmed')
    from preservation_gate import check_restoration
    from execution_scope import ROOT
    if config.get('batch_schema')==2 and 'meaningful_readiness' in scope.get('preservation',{}):
        check_meaningful_readiness(config,scope,ROOT)
    elif config['phase'] == 'copilot-smoke' and 'smoke_readiness' in scope.get('preservation', {}):
        check_smoke_readiness(config, scope, ROOT)
    else:
        check_restoration(scope, ROOT)
    acceptance = None
    if config['phase'] == 'comparison':
        acceptance = check_acceptance(config, scope['live_acceptance'], path.parent)
    reservation = reservation_path(config)
    if reservation.exists() and (run_id is None or read(reservation)['run_id'] != run_id):
        raise ValueError('Start already consumed; automatic reimplementation forbidden')
    result = {'scope_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if acceptance is not None: result['acceptance'] = acceptance
    return result


def check_meaningful_readiness(config,scope,root):
    """New, explicitly authorized protocol; never reinterpret a legacy restore proof."""
    from preservation_gate import archive_root
    from preserve import verify_receipt,digest,safe_name
    from prepare_workspace import render_contract
    archive=archive_root(scope)
    receipt=verify_receipt(archive,scope['preservation']['meaningful_readiness'])
    package=archive/'packages'/receipt['reference']['package_id']
    if read(package/'package.json')['metadata'].get('kind')!='meaningful-evaluation-readiness':
        raise ValueError('Wrong readiness evidence kind')
    proof=read(package/'payload/proof.json')
    if (proof.get('schema_version')!=2 or proof.get('settings_sha256')!=settings_hash(config)
            or proof.get('contract_sha256')!=hashlib.sha256(render_contract(root,config)).hexdigest()
            or proof.get('evaluator_files')!=config.get('evaluator_files')
            or proof.get('score_version')!=config.get('score_version')):
        raise ValueError('Readiness execution/evaluator/contract mismatch')
    required={'contract','parallel_recovery','gateway_protocols','monitor','calibration','same_submission_rescore','real_restored_analysis','runtime_restoration','independent_review'}
    if set(proof.get('checks',{}))!=required:raise ValueError('Readiness check inventory incomplete')
    for check in proof['checks'].values():
        if check.get('passed') is not True or not check.get('evidence'):raise ValueError('Readiness check unconfirmed')
        for ref in check['evidence']:
            safe_name(ref['path'])
            if digest(package/'payload'/ref['path'])!=ref['sha256']:raise ValueError('Readiness evidence changed')
    hashes=proof.get('source_hashes',{})
    if not {'scripts/copilot_scope.py','scripts/copilot_parallel.py','scripts/copilot_recovery.py','scripts/model_gateway.py','scripts/run_copilot.py','scripts/run_experiment.py','scripts/prepare_workspace.py','evaluation/prepare-app-container.py'}.issubset(hashes):
        raise ValueError('Readiness management dependencies missing')
    for name,expected in hashes.items():
        safe_name(name)
        if digest(root/name)!=expected:raise ValueError('Readiness source dependency changed: '+name)


def check_smoke_readiness(config, scope, root):
    """Bounded, unscored smoke needs restored execution evidence, not E2E calibration."""
    from preservation_gate import archive_root
    from preserve import verify_receipt, digest
    if config['phase'] != 'copilot-smoke':
        raise ValueError('Short readiness is only valid for smoke')
    archive = archive_root(scope)
    receipt = verify_receipt(archive, scope['preservation']['smoke_readiness'])
    package = archive / 'packages' / receipt['reference']['package_id']
    if read(package / 'package.json')['metadata'].get('kind') != 'copilot-smoke-readiness':
        raise ValueError('Wrong smoke readiness package')
    proof = read(package / 'payload/proof.json')
    required = {'file_edit', 'tool_execution', 'continuation', 'delegation_tools_absent',
                'native_response_reconciliation'}
    if (proof.get('settings_sha256') != settings_hash(config)
            or proof.get('model_called') is not False
            or not all(proof.get(k) is True for k in required)):
        raise ValueError('Incomplete or mismatched smoke readiness')
    hashes = proof.get('source_hashes', {})
    if not {'scripts/run_copilot.py', 'scripts/copilot_scope.py', 'scripts/model_gateway.py',
            'scripts/run_experiment.py', 'scripts/telemetry_link.py'}.issubset(hashes):
        raise ValueError('Smoke execution source pins missing')
    for relative, expected in hashes.items():
        if digest(root / relative) != expected:
            raise ValueError('Smoke execution source changed: ' + relative)


def reserve(config, run_id):
    check(config)
    write_new(reservation_path(config), {'run_id': run_id, 'settings_sha256': settings_hash(config)})

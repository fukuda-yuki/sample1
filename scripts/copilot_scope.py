"""Separate, researcher-owned Copilot starts; old pilot reservations stay untouched."""
import hashlib
import json
from pathlib import Path
from preserve import read, write_new


FIXED = ('agent', 'provider', 'base_url', 'wire_api', 'model_id', 'agent_version',
         'experiment_version', 'experiment_id', 'budget', 'subagent_policy', 'environment', 'effort')


def settings_hash(config):
    return hashlib.sha256(json.dumps({k: config[k] for k in FIXED}, sort_keys=True).encode()).hexdigest()


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
    check_restoration(scope, ROOT)
    if config['phase'] == 'comparison':
        evidence = read(path.parent / scope['live_acceptance']['path'])
        if hashlib.sha256((path.parent / scope['live_acceptance']['path']).read_bytes()).hexdigest() != scope['live_acceptance']['sha256']:
            raise ValueError('Live acceptance hash mismatch')
        if (evidence.get('settings_sha256') != settings_hash(config)
                or evidence.get('kind') != 'real-copilot-muse'
                or not all(evidence.get(k) is True for k in
                           ('file_edit', 'tool_execution', 'model_continuation', 'usage_reconciled',
                            'monitor_readback', 'independent_evaluation', 'preservation_verified'))):
            raise ValueError('Same-path real acceptance is missing')
    reservation = path.parent / 'starts' / (slot + '.json')
    if reservation.exists() and (run_id is None or read(reservation)['run_id'] != run_id):
        raise ValueError('Start already consumed; automatic reimplementation forbidden')
    return {'scope_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def reserve(config, run_id):
    check(config)
    write_new(Path(config['authorization_file']).resolve().parent / 'starts' /
              (config['planned_run'] + '.json'), {'run_id': run_id, 'settings_sha256': settings_hash(config)})

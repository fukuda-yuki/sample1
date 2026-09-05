"""Researcher-owned current authorization, never authorization embedded in a Run."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_start(config):
    scope_file = ROOT / 'config/execution-scope.json'
    scope_bytes = scope_file.read_bytes()
    scope = json.loads(scope_bytes.decode('utf-8-sig'))
    if not isinstance(scope.get('do_not_start'), list):
        raise ValueError('Execution scope: explicit forbidden Run list required')
    order = json.loads((ROOT / 'config/execution-order.json').read_text(encoding='utf-8-sig'))
    if config.get('experiment_version') != scope['experiment_version'] or order['experiment_version'] != scope['experiment_version']:
        raise ValueError('Execution scope: experiment version mismatch')
    entry = next((r for r in order['order'] if r['planned_run'] == config.get('planned_run')), None)
    if entry is None or any(config.get(k) != v for k, v in entry.items()):
        raise ValueError('Execution scope: unknown or mismatched planned Run')
    if config['planned_run'] in scope['do_not_start']:
        raise ValueError('Execution scope: Run is explicitly forbidden')
    if scope['authorized_scope'] == 'finish_or_adjudicate_existing_pilots_then_stop':
        raise ValueError('Execution scope: no new implementation Runs; existing submissions may only be evaluated')
    # A future resumption must explicitly authorize individual planned Runs.
    allowed = scope.get('allowed_starts')
    if scope['authorized_scope'] != 'explicit_planned_runs' or not isinstance(allowed, list) or config['planned_run'] not in allowed:
        raise ValueError('Execution scope: no explicit authorization to start this Run')
    return {'scope_sha256': hashlib.sha256(scope_bytes).hexdigest(),
            'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

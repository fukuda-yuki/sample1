"""Single-use fixed-input diagnostics; permission is always researcher-owned."""
import hashlib
import json
from pathlib import Path

PROMPT = 'Reply with exactly OK. Do not use tools.'
SPEC = 'Integration smoke test only. No implementation task.'


def check(config, root, run_id=None):
    from preserve import read, safe_name
    from preservation_gate import check_restoration
    scope_file = root / 'config/execution-scope.json'
    scope = read(scope_file)
    diagnostics = scope.get('diagnostics', {})
    planned = config.get('planned_run')
    if not planned or planned not in diagnostics.get('allowed_starts', []):
        raise ValueError('No explicit authorization for this diagnostic')
    safe_name(planned)
    approval = diagnostics.get('starts', {}).get(planned)
    if not isinstance(approval, dict):
        raise ValueError('Diagnostic requires an individual budget')
    budget = approval.get('budget', {})
    if (budget.get('kind') != 'wall_clock_seconds' or budget.get('scope') != 'container'
            or type(budget.get('value')) is not int or budget['value'] <= 0
            or config.get('budget') != budget):
        raise ValueError('Diagnostic budget must match the individual authorization')
    fixed = read(root / 'config/experiment.json')
    for key in ('model_id', 'effort', 'agent_version', 'tool_versions', 'subagent_policy'):
        if config.get(key) != fixed[key]:
            raise ValueError('Diagnostic setting differs from pilot: ' + key)
    for key, value in fixed['environment'].items():
        if config.get('environment', {}).get(key) != value:
            raise ValueError('Diagnostic environment differs from pilot: ' + key)
    if (config.get('phase') != 'diagnostic' or config.get('condition') != 'diagnostic'
            or config.get('experiment_version') != 'model-smoke-only'):
        raise ValueError('Diagnostic must be excluded from experiment comparisons')
    if 'command' in config:
        from run_codex import worker_command
        if config['command'] != worker_command(config, PROMPT):
            raise ValueError('Diagnostic only permits the fixed smoke command')
    archive = check_restoration(scope, root)
    reservation = archive / 'starts/diagnostics' / (planned + '.json')
    if reservation.exists() and (run_id is None or read(reservation)['run_id'] != run_id):
        raise ValueError('Diagnostic already consumed; no automatic retry')
    return {'scope_sha256': hashlib.sha256(scope_file.read_bytes()).hexdigest(),
            'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'kind': 'diagnostic'}


def reserve(config, root, run_id):
    from preserve import read, write_new
    from preservation_gate import archive_root
    check(config, root)
    archive = archive_root(read(root / 'config/execution-scope.json'))
    write_new(archive / 'starts/diagnostics' / (config['planned_run'] + '.json'),
              {'run_id': run_id, 'planned_run': config['planned_run'], 'kind': 'diagnostic'})


def validate_distribution(distribution):
    from run_experiment import snapshot
    expected = {'spec.md': hashlib.sha256(SPEC.encode('utf-8')).hexdigest()}
    record = json.loads((distribution / 'distribution.json').read_text(encoding='utf-8'))
    if (snapshot(distribution / 'workspace', source_only=False) != expected
            or record.get('condition') != 'diagnostic'
            or {name: entry['sha256'] for name, entry in record['files'].items()} != expected):
        raise ValueError('Diagnostic distribution differs from the fixed smoke input')

"""Fixed real-provider diagnostic. Never part of experiment comparisons."""
import argparse
import json
from pathlib import Path
from diagnostic_scope import SPEC
from execution_scope import check_start, ROOT
from preserve import read, write_new
from run_codex import execute_diagnostic
from run_experiment import snapshot


def configuration(planned_run):
    fixed = read(ROOT / 'config/experiment.json')
    scope = read(ROOT / 'config/execution-scope.json')
    approval = scope.get('diagnostics', {}).get('starts', {}).get(planned_run, {})
    config = {key: fixed[key] for key in ('model_id', 'effort', 'agent_version',
              'tool_versions', 'subagent_policy', 'environment')}
    config.update(experiment_version='model-smoke-only', phase='diagnostic', condition='diagnostic',
                  planned_run=planned_run, execution_order=0, budget=approval.get('budget'))
    check_start(config)  # No directories, reservations or credentials before approval.
    return config


def main(planned_run, auth, output):
    config = configuration(planned_run)
    output.mkdir(parents=True, exist_ok=False)
    distribution = output / 'distribution'
    workspace = distribution / 'workspace'
    workspace.mkdir(parents=True)
    (workspace / 'spec.md').write_text(SPEC, encoding='utf-8')
    write_new(distribution / 'distribution.json', {'condition': 'diagnostic',
              'files': {k: {'sha256': v} for k, v in snapshot(workspace).items()}})
    result = execute_diagnostic(distribution, config, output / 'run', auth)
    usage = read(output / 'run/usage.json')
    native = read(output / 'run/native-usage.json') if (output / 'run/native-usage.json').exists() else []
    preservation = read(output / 'run/preservation.json')
    passed = (result['end_reason'] == 'agent_completed' and usage['usage_complete'] is True
              and bool(native) and usage.get('native_reconciliation', {}).get('matched') is True
              and preservation['restore_verified'] is True)
    write_new(output / 'evidence.json', {'kind': 'model_usage_smoke', 'phase': 'diagnostic',
              'excluded_from_comparisons': True, 'passed': passed,
              'run_id': result['run_id'], 'end_reason': result['end_reason'],
              'usage': usage, 'native_usage': native, 'preservation': preservation,
              'model_id': config['model_id'], 'effort': config['effort']})
    if not passed:
        raise ValueError('Diagnostic failed; originals retained, no automatic retry')
    print(json.dumps({'run_id': result['run_id'], 'passed': passed, 'evidence': str(output / 'evidence.json')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--planned-run', required=True)
    p.add_argument('--auth', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    main(a.planned_run, a.auth, a.output)

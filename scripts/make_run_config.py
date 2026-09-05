"""Resolve one pre-randomized Run and record researcher-side code provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from execution_scope import check_start


def make(planned_run, output):
    root = Path(__file__).resolve().parents[1]
    base = json.loads((root / 'config/experiment.json').read_text(encoding='utf-8-sig'))
    order = json.loads((root / 'config/execution-order.json').read_text(encoding='utf-8-sig'))
    entry = next((r for r in order['order'] if r['planned_run'] == planned_run), None)
    if entry is None or base['experiment_version'] != order['experiment_version']:
        raise ValueError('Unknown Run or inconsistent experiment version')
    sources = ['run_experiment.py', 'run_codex.py', 'model_gateway.py', 'gateway_usage.py', 'normalize_usage.py', 'execution_scope.py']
    base.update(entry)
    base['start_authorization'] = check_start(base)
    base['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    base['runner_sources'] = {name: hashlib.sha256((root / 'scripts' / name).read_bytes()).hexdigest() for name in sources}
    with output.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(base, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('planned_run')
    p.add_argument('output', type=Path)
    a = p.parse_args()
    make(a.planned_run, a.output)

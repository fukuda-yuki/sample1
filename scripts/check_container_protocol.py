"""Integration checks using a real offline container. No model calls."""
import argparse
import json
from pathlib import Path
import tempfile
from run_experiment import run, snapshot


def main(image, evidence):
    results = []
    with tempfile.TemporaryDirectory(prefix='sample1-check-') as d:
        root = Path(d)
        (root / 'distribution/workspace').mkdir(parents=True)
        (root / 'host-canary').write_text('PRIVATE', encoding='utf-8')
        (root / 'distribution/workspace/spec.md').write_text('public test input', encoding='utf-8')
        distribution = {'files': {k: {'sha256': v} for k, v in snapshot(root / 'distribution/workspace').items()}}
        (root / 'distribution/distribution.json').write_text(json.dumps(distribution), encoding='utf-8')
        isolation = """import os, pathlib, socket, json
assert not pathlib.Path('/workspace/.git').exists()
assert not pathlib.Path('/workspace/../host-canary').exists()
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not os.access('/root/.codex', os.R_OK)
s = socket.socket(); s.settimeout(2)
try:
 s.connect(('1.1.1.1',443)); raise AssertionError('external network reachable')
except OSError: pass
pathlib.Path('/workspace/result.json').write_text(json.dumps({'isolated':True}))
"""
        config = dict(experiment_version='protocol-integration-only', model_id='none', effort='none',
                      agent_version='python-test', tool_versions={}, subagent_policy='disabled', execution_order=0,
                      environment={'image': image}, budget={'kind':'wall_clock_seconds','value':30,'scope':'container'})
        for title, command, seconds, expected in [
            ('isolation', ['python','-c',isolation],30,'agent_completed'),
            ('error', ['python','-c',"open('/workspace/partial','w').write('partial');raise SystemExit(2)"],30,'agent_error'),
            ('timeout', ['python','-c',"import subprocess,time;subprocess.Popen(['python','-c',\"import time,pathlib;time.sleep(5);pathlib.Path('/workspace/late').write_text('bad')\"]);time.sleep(30)"],2,'budget_exhausted')]:
            config.update(command=command, budget={'kind':'wall_clock_seconds','value':seconds,'scope':'container'})
            result = run(root / 'distribution', config, root / title)
            assert result['end_reason'] == expected, result
            assert result['submission_fixed'] and result['processes_stopped'], result
            results.append({'case': title, 'end_reason': result['end_reason'], 'processes_stopped': True,
                            'submission_fixed': True, 'elapsed_seconds': result['elapsed_seconds']})
        import time
        time.sleep(5)
        assert not (root / 'timeout/working/late').exists()
        results.append({'case':'descendant_stopped', 'passed':True})
    evidence.write_text(json.dumps({'kind':'protocol_integration', 'model_called':False, 'results':results},indent=2),encoding='utf-8')


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--image', required=True)
    p.add_argument('--evidence', required=True, type=Path)
    a=p.parse_args()
    main(a.image,a.evidence)

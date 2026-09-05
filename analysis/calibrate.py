"""Save explicitly synthetic edge cases for score/plot calibration."""
import json
from pathlib import Path
from aggregate import aggregate, write_outputs
from test_aggregate import fixture, LEDGER


def generate(out):
    runs, results = [], []
    scenarios = [('full', 'agent_completed'), ('zero', 'agent_error'),
                 ('partial', 'agent_completed'), ('blocked', 'environment_failure'),
                 ('limit', 'budget_exhausted'), ('eval-error', 'agent_completed'),
                 ('missing-usage', 'agent_completed'), ('aborted', 'operator_aborted')]
    for i, (name, reason) in enumerate(scenarios):
        rr, ee = fixture()
        rr[0].update(run_id='synthetic-' + name, condition='normal' if i % 2 == 0 else 'anti',
                     end_reason=reason, total_tokens=(i + 1) * 1000)
        for j, e in enumerate(ee):
            e['run_id'] = rr[0]['run_id']
            if name == 'zero':
                e['status'] = 'fail'
            if name in ('partial', 'limit', 'aborted') and j % 3 == 0:
                e['status'] = 'fail'
            if name == 'blocked':
                e['status'] = 'blocked'
            if name == 'eval-error' and j == 0:
                e['status'] = 'error'
        if name == 'missing-usage':
            rr[0].update(usage_complete=False, total_tokens=None)
        runs.extend(rr)
        results.extend(ee)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'synthetic-runs.json').write_text(json.dumps(runs, indent=2), encoding='utf-8')
    (out / 'synthetic-results.jsonl').write_text('\n'.join(json.dumps(r) for r in results) + '\n', encoding='utf-8')
    write_outputs(*aggregate(runs, results, LEDGER), out)


if __name__ == '__main__':
    import sys
    generate(Path(sys.argv[1]))

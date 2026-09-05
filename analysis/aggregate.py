"""Fixed-ID aggregation. No implementation self-tests enter this score."""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {'pass', 'fail', 'blocked', 'error'}


def aggregate(runs, results, ledger):
    ids = {x['evaluation_id']: x for x in ledger['items']}
    if len(ids) != ledger['fixed_denominator'] or len(ids) != len(ledger['items']):
        raise ValueError('Ledger denominator mismatch')
    run_index = {r['run_id']: r for r in runs}
    if len(run_index) != len(runs):
        raise ValueError('Duplicate Run ID')
    grouped = {}
    for result in results:
        rid, eid, case = (result[k] for k in ('run_id', 'evaluation_id', 'case_id'))
        if rid not in run_index or eid not in ids or result['status'] not in STATUSES:
            raise ValueError('Unknown run, evaluation ID or status')
        required = {'lower', 'upper'} if eid == 'T-006-05' else {'main'}
        if case not in required:
            raise ValueError('Unknown required case: ' + case)
        for field in ('score_version', 'submission_hash'):
            if result[field] != run_index[rid][field]:
                raise ValueError('Evaluation version or submission mismatch')
        key = (rid, eid, case)
        if key in grouped:
            raise ValueError('Duplicate case result; select one evaluation attempt explicitly')
        grouped[key] = result
    rows, details = [], []
    for run in sorted(runs, key=lambda r: r['run_id']):
        if run['phase'] not in ('calibration', 'pilot', 'comparison') or run['condition'] not in ('normal', 'anti'):
            raise ValueError('Invalid phase or condition')
        validity = run.get('evaluation_validity', 'pending')
        if validity not in ('valid', 'invalid', 'pending'):
            raise ValueError('Unknown evaluation validity')
        expected_kind = 'calibration' if run['phase'] == 'calibration' else 'evaluation'
        if run.get('evaluation_kind') not in (None, expected_kind):
            raise ValueError('Evaluation kind does not match Run phase')
        effective_valid = (validity == 'valid' and run.get('evaluation_kind') == expected_kind
                           and bool(run.get('validity_record_hash')))
        if validity == 'valid' and not effective_valid:
            validity = 'pending'
        validity_reason = run.get('validity_reason') or ('Missing evaluation validity evidence' if not effective_valid else '')
        count = {s: 0 for s in STATUSES}
        for eid, item in ids.items():
            cases = ('lower', 'upper') if eid == 'T-006-05' else ('main',)
            entries = [grouped.get((run['run_id'], eid, c), {
                'case_id': c, 'status': 'blocked', 'evidence': 'Required case not evaluated'
            }) for c in cases]
            statuses = {e['status'] for e in entries}
            status = next(s for s in ('error', 'fail', 'blocked', 'pass') if s in statuses)
            count[status] += 1
            details.append(dict(run_id=run['run_id'], evaluation_id=eid, status=status,
                                ap001_relation=item['ap001_relation'], cases=entries,
                                evaluation_validity=validity, validity_reason=validity_reason,
                                validity_record_hash=run.get('validity_record_hash')))
        total = run.get('total_tokens')
        complete = run.get('usage_complete') is True and type(total) is int and total >= 0
        if run.get('usage_complete') is True and total is not None and not complete:
            raise ValueError('Complete usage requires a nonnegative integer total')
        quality = None if count['error'] or run.get('evaluation_error') or not effective_valid else 100 * count['pass'] / len(ids)
        row = {k: run[k] for k in ('run_id', 'phase', 'condition', 'experiment_version',
                                  'score_version', 'submission_hash', 'end_reason')}
        for field in ('evaluation_attempt', 'evaluation_id', 'evaluation_kind', 'ledger_hash', 'manifest_hash', 'usage_hash', 'results_hash', 'validity_record_hash', 'validity_registry_hash'):
            row[field] = run.get(field)
        row.update(evaluation_validity=validity, validity_reason=validity_reason)
        row.update(total_tokens=total if complete else None, usage_complete=complete,
                   observed_tokens=run.get('observed_tokens'), denominator=len(ids),
                   passed=count['pass'], failed=count['fail'], blocked=count['blocked'],
                   errors=count['error'], quality_percent=quality,
                   all_passed=(count['pass'] == len(ids)) if quality is not None else None,
                   evaluation_error=run.get('evaluation_error', ''),
                   missing_reason=('usage incomplete; ' if not complete else '') +
                                  (validity_reason or run.get('evaluation_error') or 'evaluation unavailable' if quality is None else ''))
        rows.append(row)
    return rows, details


def write_outputs(rows, details, out):
    out.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError('No runs to aggregate')
    with (out / 'runs.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (out / 'test-results.jsonl').open('w', encoding='utf-8') as f:
        for row in details:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--runs', type=Path, required=True)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--ledger', type=Path, default=ROOT / 'evaluation/requirements-ledger.json')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    rows, details = aggregate(json.loads(args.runs.read_text(encoding='utf-8-sig')),
                              [json.loads(line) for line in args.results.read_text(encoding='utf-8-sig').splitlines() if line.strip()],
                              json.loads(args.ledger.read_text(encoding='utf-8-sig')))
    write_outputs(rows, details, args.out)
    print(f'{len(rows)} runs; {len(details)} fixed-ID results')

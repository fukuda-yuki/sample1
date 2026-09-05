"""Join selected immutable Run/evaluation attempts without dropping failures."""
import argparse
import hashlib
import json
from pathlib import Path
from aggregate import aggregate, write_outputs, ROOT


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(selections, ledger_path=ROOT / 'evaluation/requirements-ledger.json'):
    ledger = read(ledger_path)
    ledger_hash = digest(ledger_path)
    required = {(item['evaluation_id'], case) for item in ledger['items']
                for case in (('lower', 'upper') if item['evaluation_id'] == 'T-006-05' else ('main',))}
    runs, results = [], []
    for selected in selections:
        directory = Path(selected['run_directory'])
        manifest_file, usage_file = directory / 'manifest.json', directory / 'usage.json'
        manifest, usage = read(manifest_file), read(usage_file)
        base = dict(run_id=manifest['run_id'], phase=manifest['phase'],
                    condition=manifest['distribution']['condition'], experiment_version=manifest['experiment_version'],
                    end_reason=manifest['end_reason'], usage_complete=usage['usage_complete'],
                    total_tokens=usage['total_tokens'], observed_tokens=usage.get('observed_tokens'),
                    manifest_hash=digest(manifest_file), usage_hash=digest(usage_file), ledger_hash=ledger_hash)
        if selected['evaluation_directory'] is None:
            # Explicitly absent evaluation is missing quality, never 57 implementation failures.
            base.update(score_version=None, submission_hash=None, evaluation_attempt=None,
                        results_hash=None, evaluation_error='No evaluation selected')
            runs.append(base)
            continue
        evaluation = Path(selected['evaluation_directory'])
        summary = read(evaluation / 'summary.json')
        if manifest['run_id'] != summary['run_id']:
            raise ValueError('Run/evaluation identity mismatch')
        if summary['ledger_hash'] != ledger_hash:
            raise ValueError('Evaluation ledger mismatch; select the exact frozen ledger with --ledger')
        if summary['outcome'] not in ('completed', 'server_unavailable', 'evaluator_error', 'isolation_blocked'):
            raise ValueError('Unknown evaluation outcome')
        evaluation_error = summary['outcome'] in ('evaluator_error', 'isolation_blocked')
        snapshot_file = directory / 'snapshot.json'
        if snapshot_file.exists():
            expected_hash = digest(snapshot_file)
            if summary['submission_hash'] != expected_hash and not (summary['submission_hash'] is None and evaluation_error):
                raise ValueError('Wrong fixed submission evaluated')
        elif not evaluation_error:
            raise ValueError('Scored evaluation requires the Run snapshot')
        rows = [json.loads(s) for s in (evaluation / 'results.jsonl').read_text(encoding='utf-8-sig').splitlines() if s]
        if len(rows) != len(required) or {(r['evaluation_id'], r['case_id']) for r in rows} != required:
            raise ValueError('Incomplete or duplicated evaluator result file')
        run = dict(base, score_version=summary['evaluator_hash'], submission_hash=summary['submission_hash'],
                   evaluation_attempt=str(evaluation.resolve()), results_hash=digest(evaluation / 'results.jsonl'))
        if evaluation_error:
            run['evaluation_error'] = summary.get('error') or summary['outcome']
        # Reject silent report truncation, wrong cases and altered summary metrics.
        calculated, _ = aggregate([run], rows, ledger)
        row = calculated[0]
        expected_counts = {'denominator': row['denominator'], 'pass': row['passed'], 'fail': row['failed'],
                           'blocked': row['blocked'], 'error': row['errors']}
        if summary['counts'] != expected_counts:
            raise ValueError('Summary/result counts mismatch')
        quality = None if row['quality_percent'] is None else row['passed'] / row['denominator']
        if summary['quality'] != quality:
            raise ValueError('Summary/result quality mismatch')
        runs.append(run)
        results.extend(rows)
    return runs, results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('selections', type=Path, help='Explicit list of Run and selected evaluation directories')
    parser.add_argument('output', type=Path)
    parser.add_argument('--ledger', type=Path, default=ROOT / 'evaluation/requirements-ledger.json')
    args = parser.parse_args()
    runs, results = collect(read(args.selections), args.ledger)
    write_outputs(*aggregate(runs, results, read(args.ledger)), args.output)

import copy
import json
from pathlib import Path
import unittest
from aggregate import aggregate

LEDGER = json.loads((Path(__file__).resolve().parents[1] / 'evaluation/requirements-ledger.json').read_text(encoding='utf-8'))


def fixture():
    run = dict(run_id='synth-1', phase='calibration', condition='normal', experiment_version='synthetic',
               score_version='synthetic', submission_hash='synthetic', end_reason='agent_completed',
               total_tokens=100, usage_complete=True, evaluation_kind='calibration',
               evaluation_validity='valid', validity_record_hash='synthetic-evidence', validity_reason='Synthetic calibration')
    results = []
    for item in LEDGER['items']:
        eid = item['evaluation_id']
        for case in (('lower', 'upper') if eid == 'T-006-05' else ('main',)):
            results.append(dict(run_id=run['run_id'], evaluation_id=eid, case_id=case, status='pass',
                                evidence='synthetic calibration', score_version='synthetic', submission_hash='synthetic'))
    return [run], results


class AggregationTests(unittest.TestCase):
    def test_full_and_empty(self):
        runs, results = fixture()
        rows, _ = aggregate(runs, results, LEDGER)
        self.assertEqual((rows[0]['quality_percent'], rows[0]['denominator'], rows[0]['all_passed']), (100, 57, True))
        rows, _ = aggregate(runs, [], LEDGER)
        self.assertEqual((rows[0]['quality_percent'], rows[0]['blocked']), (0, 57))

    def test_partial_and_two_cases_are_one_point(self):
        runs, results = fixture()
        target = next(r for r in results if r['case_id'] == 'upper')
        target['status'] = 'fail'
        rows, _ = aggregate(runs, results, LEDGER)
        self.assertAlmostEqual(rows[0]['quality_percent'], 100 * 56 / 57)
        self.assertEqual(rows[0]['failed'], 1)
        results.remove(target)
        rows, _ = aggregate(runs, results, LEDGER)
        self.assertEqual((rows[0]['passed'], rows[0]['blocked']), (56, 1))

    def test_evaluator_error_is_not_zero(self):
        runs, results = fixture()
        results[0]['status'] = 'error'
        rows, _ = aggregate(runs, results, LEDGER)
        self.assertIsNone(rows[0]['quality_percent'])
        self.assertIsNone(rows[0]['all_passed'])

    def test_usage_missing_and_limit_retained(self):
        runs, results = fixture()
        runs[0].update(usage_complete=False, total_tokens=None, end_reason='budget_exhausted')
        rows, _ = aggregate(runs, results, LEDGER)
        self.assertIsNone(rows[0]['total_tokens'])
        self.assertEqual(rows[0]['quality_percent'], 100)
        self.assertEqual(rows[0]['end_reason'], 'budget_exhausted')

    def test_null_total_is_missing_even_with_complete_flag(self):
        runs, results = fixture()
        runs[0]['total_tokens'] = None
        row = aggregate(runs, results, LEDGER)[0][0]
        self.assertIsNone(row['total_tokens'])
        self.assertFalse(row['usage_complete'])

    def test_duplicate_ledger_item_is_rejected(self):
        runs, results = fixture()
        ledger = copy.deepcopy(LEDGER)
        ledger['items'].append(copy.deepcopy(ledger['items'][0]))
        with self.assertRaises(ValueError):
            aggregate(runs, results, ledger)

    def test_reject_duplicate_unknown_and_mismatch(self):
        for field, value in [('evaluation_id', 'unknown'), ('case_id', 'split'), ('score_version', 'other'), ('submission_hash', 'other')]:
            runs, results = fixture()
            results[0][field] = value
            with self.assertRaises(ValueError):
                aggregate(runs, results, LEDGER)
        runs, results = fixture()
        with self.assertRaises(ValueError):
            aggregate(runs, results + [copy.deepcopy(results[0])], LEDGER)

    def test_direct_call_without_validity_is_pending(self):
        runs,results=fixture()
        runs[0].pop('evaluation_validity')
        row=aggregate(runs,results,LEDGER)[0][0]
        self.assertIsNone(row['quality_percent'])
        self.assertIsNone(row['all_passed'])

    def test_deterministic(self):
        runs, results = fixture()
        self.assertEqual(aggregate(runs, results, LEDGER), aggregate(runs, list(reversed(results)), LEDGER))


if __name__ == '__main__':
    unittest.main()

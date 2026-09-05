"""Real archive/collector checks for predecessor eligibility; no model calls."""
import copy
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from preservation_gate import check
from preserve import digest, pack, read, restore


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class PredecessorGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'archive'
        self.current = self.root / 'researcher/current-validity.json'
        self.scope = {'batch_id': 'batch', 'planned_manifest': 'order.json', 'preservation': {
            'current_validity_registry': {'windows': str(self.current), 'linux': str(self.current)}}}
        self.config = {'planned_run': 'second'}
        save(self.root / 'order.json', {'order': [{'planned_run': 'first'}, {'planned_run': 'second'}]})
        # Restoration proof is tested in test_preservation; archive/receipt and
        # collector/aggregation/registry verification below are all real.
        self.restoration = patch('preservation_gate.check_restoration', return_value=self.archive)
        self.restoration.start()
        self.addCleanup(self.restoration.stop)

    def build(self, status='pass', outcome='completed', complete=True, total=12):
        run = self.root / 'source-run'
        evaluation = self.root / 'source-evaluation'
        result = evaluation / 'attempt-1'
        save(run / 'manifest.json', {'run_id': 'run-1', 'phase': 'pilot', 'distribution': {'condition': 'normal'},
            'experiment_version': 'test', 'end_reason': 'agent_completed'})
        save(run / 'usage.json', {'usage_complete': complete, 'total_tokens': total})
        save(run / 'snapshot.json', {'file': 'synthetic submission'})
        ledger = result / 'evaluator-snapshot/requirements-ledger.json'
        save(ledger, {'fixed_denominator': 1, 'items': [{'evaluation_id': 'T-001-01', 'ap001_relation': 'none'}]})
        submission = digest(run / 'snapshot.json')
        summary = {'kind': 'evaluation', 'run_id': 'run-1', 'submission_hash': submission,
            'evaluator_hash': 'test-evaluator', 'ledger_hash': digest(ledger), 'outcome': outcome,
            'quality': None if status == 'error' or outcome == 'evaluator_error' else (1 if status == 'pass' else 0),
            'counts': {'denominator': 1, **{s: int(s == status) for s in ('pass', 'fail', 'blocked', 'error')}}}
        save(result / 'summary.json', summary)
        row = {'run_id': 'run-1', 'evaluation_id': 'T-001-01', 'case_id': 'main', 'status': status,
               'score_version': 'test-evaluator', 'submission_hash': submission}
        (result / 'results.jsonl').write_text(json.dumps(row) + '\n', encoding='utf-8')
        registry = {'schema_version': 1, 'attempts': [{'evaluation_id': 'attempt-1', 'status': 'valid',
            'reason': 'synthetic eligibility fixture', **{k: summary[k] for k in ('run_id', 'submission_hash', 'evaluator_hash')},
            'summary_hash': digest(result / 'summary.json'), 'results_hash': digest(result / 'results.jsonl')}]}
        save(evaluation / 'evaluation-validity.json', registry)
        save(self.current, registry)
        run_ref = pack(self.archive, 'run-1', {p.name: p for p in run.iterdir()}, metadata={'missing': []})
        eval_ref = pack(self.archive, 'evaluation-1', {p.name: p for p in evaluation.iterdir()})
        run_receipt = restore(self.archive, run_ref, self.root / 'restored-run')
        eval_receipt = restore(self.archive, eval_ref, self.root / 'restored-evaluation')
        save(self.archive / 'starts/batch/first.json', {'run_id': 'run-1'})
        save(self.archive / 'completed/batch/first.json', {'run_id': 'run-1', 'run_receipt': run_receipt,
            'evaluation_receipt': eval_receipt, 'evaluation_directory': 'attempt-1'})

    def check(self):
        return check(self.scope, self.config, self.root)

    def test_valid_quality_and_zero_quality_pass(self):
        self.build(status='fail')
        before = {p: p.read_bytes() for p in self.archive.rglob('*') if p.is_file()}
        self.assertEqual(self.check(), self.archive)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_valid_full_quality_passes(self):
        self.build()
        self.assertEqual(self.check(), self.archive)

    def test_evaluator_error_even_with_valid_registry_rejected(self):
        self.build(outcome='evaluator_error')
        with self.assertRaisesRegex(ValueError, 'not valid'):
            self.check()

    def test_case_error_null_quality_rejected(self):
        self.build(status='error')
        with self.assertRaisesRegex(ValueError, 'not valid'):
            self.check()

    def test_incomplete_usage_rejected(self):
        self.build(complete=False, total=None)
        with self.assertRaisesRegex(ValueError, 'not valid'):
            self.check()

    def test_claimed_complete_but_missing_total_rejected(self):
        self.build(complete=True, total=None)
        with self.assertRaisesRegex(ValueError, 'not valid'):
            self.check()

    def test_current_invalid_pending_missing_record_reject_archived_valid(self):
        self.build()
        original = read(self.current)
        for status in ('invalid', 'pending', 'missing'):
            with self.subTest(status=status):
                registry = copy.deepcopy(original)
                if status == 'missing':
                    registry['attempts'] = []
                else:
                    registry['attempts'][0]['status'] = status
                save(self.current, registry)
                with self.assertRaisesRegex(ValueError, 'not valid'):
                    self.check()
        save(self.current, original)
        self.assertEqual(self.check(), self.archive)

    def test_current_identity_bindings_rejected(self):
        self.build()
        original = read(self.current)
        for field in ('evaluation_id', 'run_id', 'submission_hash', 'evaluator_hash', 'summary_hash', 'results_hash'):
            with self.subTest(field=field):
                registry = copy.deepcopy(original)
                registry['attempts'][0][field] = 'mismatch'
                save(self.current, registry)
                with self.assertRaises(ValueError):
                    self.check()

    def test_missing_current_registry_file_or_setting_rejected(self):
        self.build()
        self.current.unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()
        del self.scope['preservation']['current_validity_registry']
        with self.assertRaisesRegex(ValueError, 'registry required'):
            self.check()


if __name__ == '__main__':
    unittest.main()

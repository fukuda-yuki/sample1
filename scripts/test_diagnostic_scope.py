"""Diagnostic authorization and fixed-input boundaries, without model calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import diagnostic_scope
from execution_scope import ROOT, check_start, reserve_start
from run_codex import execute, execute_diagnostic, worker_command
from run_experiment import run, snapshot
import smoke_model

sys.path.insert(0, str(ROOT / 'analysis'))
from aggregate import aggregate


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def config_from(fixed):
    config = {key: copy.deepcopy(fixed[key]) for key in ('model_id', 'effort', 'agent_version',
              'tool_versions', 'subagent_policy', 'environment')}
    config.update(experiment_version='model-smoke-only', phase='diagnostic', condition='diagnostic',
                  planned_run='smoke-test', execution_order=0,
                  budget={'kind': 'wall_clock_seconds', 'scope': 'container', 'value': 10})
    return config


class CurrentDiagnosticStopTests(unittest.TestCase):
    def test_actual_scope_refuses_every_entry_before_side_effects(self):
        fixed = json.loads((ROOT / 'config/experiment.json').read_text(encoding='utf-8-sig'))
        config = config_from(fixed)
        # Caller-supplied apparent approval cannot override the researcher file.
        config['start_authorization'] = {'kind': 'diagnostic', 'allowed': True}
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            with patch('subprocess.run') as process, patch('preserve.write_new') as write, \
                    patch('run_codex.uuid.uuid4') as identity:
                for entry in (
                    lambda: smoke_model.main('smoke-test', target / 'auth', target / 'smoke'),
                    lambda: execute_diagnostic(target / 'distribution', config, target / 'execute', target / 'auth'),
                    lambda: run(target / 'distribution', config, target / 'run'),
                ):
                    with self.assertRaisesRegex(ValueError, 'No explicit authorization'):
                        entry()
                process.assert_not_called()
                write.assert_not_called()
                identity.assert_not_called()
                self.assertEqual(list(target.iterdir()), [])


class DiagnosticApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'archive'
        self.fixed = json.loads((ROOT / 'config/experiment.json').read_text(encoding='utf-8-sig'))
        self.config = config_from(self.fixed)
        self.scope = {'diagnostics': {'allowed_starts': ['smoke-test'],
                      'starts': {'smoke-test': {'budget': self.config['budget']}}},
                      'preservation': {'archive': {'windows': str(self.archive), 'linux': str(self.archive)}}}
        save(self.root / 'config/experiment.json', self.fixed)
        self.save_scope()
        # Only proof verification is substituted: authorization, reservation,
        # distribution, command and analysis boundaries use production code.
        for target, value in (('execution_scope.ROOT', self.root), ('smoke_model.ROOT', self.root)):
            context = patch(target, value)
            context.start()
            self.addCleanup(context.stop)
        self.restoration = patch('preservation_gate.check_restoration', return_value=self.archive)
        self.proof = self.restoration.start()
        self.addCleanup(self.restoration.stop)

    def save_scope(self):
        save(self.root / 'config/execution-scope.json', self.scope)

    def distribution(self):
        distribution = self.root / 'distribution'
        workspace = distribution / 'workspace'
        workspace.mkdir(parents=True)
        (workspace / 'spec.md').write_text(diagnostic_scope.SPEC, encoding='utf-8')
        save(distribution / 'distribution.json', {'condition': 'diagnostic',
             'files': {k: {'sha256': v} for k, v in snapshot(workspace).items()}})
        return distribution

    def test_explicit_fixed_configuration_and_distribution_allowed(self):
        self.assertEqual(smoke_model.configuration('smoke-test'), self.config)
        command_config = dict(self.config, command=worker_command(self.config, diagnostic_scope.PROMPT))
        self.assertEqual(check_start(command_config)['kind'], 'diagnostic')
        self.proof.assert_called()
        diagnostic_scope.validate_distribution(self.distribution())
        self.assertFalse(self.archive.exists())

    def test_single_use_matching_recheck_and_revocation(self):
        reserve_start(self.config, 'run-one')
        reservation = self.archive / 'starts/diagnostics/smoke-test.json'
        before = reservation.read_bytes()
        self.assertEqual(check_start(self.config, 'run-one')['kind'], 'diagnostic')
        for operation in (lambda: check_start(self.config), lambda: check_start(self.config, 'run-two'),
                          lambda: reserve_start(self.config, 'run-two')):
            with self.assertRaisesRegex(ValueError, 'already consumed'):
                operation()
        self.scope['diagnostics']['allowed_starts'] = []
        self.save_scope()
        with self.assertRaisesRegex(ValueError, 'No explicit authorization'):
            check_start(self.config, 'run-one')
        self.assertEqual(reservation.read_bytes(), before)

    def test_missing_or_invalid_individual_budget_refused(self):
        for budget in (None, {}, {'kind': 'wall_clock_seconds', 'scope': 'container', 'value': 0},
                       {'kind': 'wall_clock_seconds', 'scope': 'container', 'value': True},
                       {'kind': 'wall_clock_seconds', 'scope': 'container', 'value': 11}):
            with self.subTest(budget=budget):
                approval = {} if budget is None else {'budget': budget}
                self.scope['diagnostics']['starts']['smoke-test'] = approval
                self.save_scope()
                with self.assertRaises(ValueError):
                    check_start(self.config)
        self.proof.assert_not_called()

    def test_wrong_fixed_settings_and_diagnostic_identity_refused(self):
        for field in ('model_id', 'effort', 'agent_version', 'tool_versions', 'subagent_policy',
                      'environment', 'condition', 'experiment_version', 'planned_run'):
            with self.subTest(field=field):
                config = copy.deepcopy(self.config)
                config[field] = {} if field in ('tool_versions', 'environment') else 'wrong'
                with self.assertRaises(ValueError):
                    check_start(config)
        self.proof.assert_not_called()

    def test_custom_command_prompt_and_wrong_entry_refused(self):
        for command in (['true'], worker_command(self.config, 'Arbitrary implementation request')):
            with self.assertRaisesRegex(ValueError, 'fixed smoke command'):
                check_start(dict(self.config, command=command))
        with self.assertRaisesRegex(ValueError, 'Custom prompts'):
            execute(self.root, self.config, self.root / 'out', self.root / 'auth', prompt='anything')
        with self.assertRaisesRegex(ValueError, 'fixed diagnostic entry'):
            execute(self.root, self.config, self.root / 'out', self.root / 'auth')
        with self.assertRaisesRegex(ValueError, 'Diagnostic phase required'):
            execute_diagnostic(self.root, dict(self.config, phase='pilot'), self.root / 'out', self.root / 'auth')
        self.proof.assert_not_called()

    def test_wrong_distribution_refused_before_reservation_and_process(self):
        distribution = self.distribution()
        spec = distribution / 'workspace/spec.md'
        spec.write_text('Modified diagnostic task', encoding='utf-8')
        with patch('subprocess.run') as process, patch('run_codex.reserve_start') as reserve:
            for entry in (lambda: execute_diagnostic(distribution, self.config, self.root / 'output', self.root / 'auth'),
                          lambda: run(distribution, self.config, self.root / 'output')):
                with self.assertRaisesRegex(ValueError, 'fixed smoke input'):
                    entry()
            process.assert_not_called()
            reserve.assert_not_called()
        self.assertFalse(self.archive.exists())
        self.assertFalse((self.root / 'output').exists())

    def test_extra_file_or_wrong_distribution_record_refused(self):
        distribution = self.distribution()
        extra = distribution / 'workspace/EXTRA.md'
        extra.write_text('extra instruction')
        with self.assertRaisesRegex(ValueError, 'fixed smoke input'):
            diagnostic_scope.validate_distribution(distribution)
        extra.unlink()
        record = json.loads((distribution / 'distribution.json').read_text())
        record['condition'] = 'normal'
        save(distribution / 'distribution.json', record)
        with self.assertRaisesRegex(ValueError, 'fixed smoke input'):
            diagnostic_scope.validate_distribution(distribution)

    def test_diagnostic_is_rejected_by_comparison_aggregation(self):
        diagnostic = dict(self.config, run_id='diagnostic-run')
        ledger = {'fixed_denominator': 1, 'items': [{'evaluation_id': 'test', 'ap001_relation': 'none'}]}
        with self.assertRaisesRegex(ValueError, 'Invalid phase or condition'):
            aggregate([diagnostic], [], ledger)


if __name__ == '__main__':
    unittest.main()

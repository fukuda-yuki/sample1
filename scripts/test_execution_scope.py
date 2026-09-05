"""Current stop instructions must stop every entry point before side effects."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from execution_scope import check_start, ROOT
from make_run_config import make
from run_codex import execute
from run_experiment import run


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.order = json.loads((ROOT / 'config/execution-order.json').read_text())
        self.config = dict(self.order['order'][0], experiment_version=self.order['experiment_version'])

    def test_all_planned_runs_rejected_before_generation_or_execution(self):
        for entry in self.order['order']:
            config = dict(entry, experiment_version=self.order['experiment_version'], start_authorization={'allowed': True})
            with self.subTest(run=entry['planned_run']), patch('subprocess.run') as docker:
                with self.assertRaises(ValueError):make(entry['planned_run'], self.root / 'config.json')
                with self.assertRaises(ValueError):execute(self.root, config, self.root / 'run', self.root / 'auth')
                with self.assertRaises(ValueError):run(self.root, config, self.root / 'run')
                docker.assert_not_called()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_unknown_mismatch_and_explicit_future_scope(self):
        (self.root / 'config').mkdir()
        (self.root / 'config/execution-order.json').write_text(json.dumps(self.order))
        scope_path = self.root / 'config/execution-scope.json'
        scope = dict(experiment_version=self.config['experiment_version'], authorized_scope='explicit_planned_runs',
                     allowed_starts=[self.config['planned_run']], do_not_start=[])
        with patch('execution_scope.ROOT', self.root):
            with self.assertRaises(FileNotFoundError):check_start(self.config)
            for change in ({'authorized_scope':'unknown'}, {'experiment_version':'wrong'},
                           {'allowed_starts':[]}, {'do_not_start':[self.config['planned_run']]}):
                scope_path.write_text(json.dumps(dict(scope, **change)))
                with self.assertRaises(ValueError):check_start(self.config)
            scope_path.write_text(json.dumps(scope))
            with self.assertRaises(ValueError):check_start(self.config)  # Explicit permission alone cannot bypass preservation.
            bad=copy.deepcopy(self.config);bad['condition']='anti'
            with self.assertRaises(ValueError):check_start(bad)
            # A previously accepted config is rechecked against current instructions.
            scope_path.write_text(json.dumps(dict(scope, allowed_starts=[])))
            with self.assertRaises(ValueError):check_start(self.config)

    def test_runner_rechecks_after_container_creation(self):
        from run_experiment import snapshot
        import subprocess
        distribution = self.root / 'distribution'
        workspace = distribution / 'workspace'
        workspace.mkdir(parents=True)
        (workspace / 'spec.md').write_text('synthetic')
        (distribution / 'distribution.json').write_text(json.dumps(
            {'files': {k: {'sha256': v} for k, v in snapshot(workspace).items()}}))
        config = dict(self.config, model_id='test', effort='test', agent_version='test', tool_versions={},
                      subagent_policy='disabled', environment={'image':'sha256:'+'a'*64}, command=['true'],
                      budget={'kind':'wall_clock_seconds','value':1,'scope':'container'})
        commands = []
        def command(args, **kwargs):
            commands.append(args)
            return subprocess.CompletedProcess(args,0,stdout='false\n' if args[1]=='inspect' else '',stderr='')
        with patch('run_experiment.reserve_start'), patch('run_experiment.check_start',side_effect=[{'scope_sha256':'old'},ValueError('Scope revoked')]), patch('run_experiment.subprocess.run',side_effect=command):
            result = run(distribution,config,self.root/'run')
        self.assertFalse(any(c[:2]==['docker','start'] for c in commands))
        self.assertEqual(result['error'],'Scope revoked')


if __name__ == '__main__':
    unittest.main()

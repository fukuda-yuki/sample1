"""Synthetic Docker/CLI responses; real runner, accounting and archive restore.

Authorization is substituted in this fixture only. This is not a provider test.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from diagnostic_scope import SPEC
from preserve import pack, read, verify_receipt
from run_codex import execute_diagnostic
from run_experiment import snapshot


class DiagnosticLifecycleTests(unittest.TestCase):
    def test_common_lifecycle_retains_success_error_timeout_and_setup_failure(self):
        for case, expected in [('success', 'agent_completed'), ('error', 'agent_error'),
                               ('timeout', 'budget_exhausted'), ('setup', 'environment_failure')]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                distribution = root / 'distribution'
                workspace = distribution / 'workspace'
                workspace.mkdir(parents=True)
                (workspace / 'spec.md').write_text(SPEC, encoding='utf-8')
                (distribution / 'distribution.json').write_text(json.dumps({'condition': 'diagnostic',
                    'files': {k: {'sha256': v} for k, v in snapshot(workspace).items()}}))
                archive = root / 'archive'
                common = pack(archive, 'synthetic-common', {'spec.md': workspace / 'spec.md'})
                (root / 'config').mkdir()
                (root / 'config/execution-scope.json').write_text(json.dumps({'preservation': {
                    'archive': {'windows': str(archive), 'linux': str(archive)}, 'common': common}}))
                config = dict(phase='diagnostic', condition='diagnostic', experiment_version='model-smoke-only',
                              model_id='synthetic', effort='xhigh', agent_version='synthetic', tool_versions={},
                              subagent_policy='disabled', execution_order=0,
                              environment={'image': 'sha256:' + 'a' * 64},
                              budget={'kind': 'wall_clock_seconds', 'value': 5, 'scope': 'container'})
                commands = []

                def docker(argv, **kwargs):
                    commands.append(argv)
                    out = ''
                    if argv[:2] == ['docker', 'start'] and argv[2].startswith('sample1-gateway-'):
                        if case == 'setup':
                            raise subprocess.CalledProcessError(1, argv, stderr=b'synthetic setup failure')
                        raw = next((root / '.raw-usage').iterdir())
                        rid = raw.name
                        event = dict(run_id=rid, event_id='one', request_id='one', session_id='implementation',
                                     model_id='synthetic', provider='synthetic', mode='request', usage=None)
                        (raw / 'started.jsonl').write_text(json.dumps(event) + '\n')
                        if case != 'timeout':
                            event['usage'] = {'input_tokens': 10, 'output_tokens': 3}
                            (raw / 'events.jsonl').write_text(json.dumps(event) + '\n')
                    if argv[:3] == ['docker', 'network', 'inspect']:
                        rid = argv[-1].removeprefix('sample1-private-')
                        out = json.dumps([{'Internal': True, 'Labels': {'sample1.run_id': rid},
                            'Options': {'com.docker.network.bridge.gateway_mode_ipv4': 'isolated'}}])
                    if argv[1] == 'wait':
                        if case == 'timeout':
                            raise subprocess.TimeoutExpired(argv, 5)
                        out = '0' if case == 'success' else '2'
                    if argv[1] == 'inspect':
                        out = 'false'
                    if argv[1] == 'logs':
                        out = '' if case == 'timeout' else json.dumps({'type': 'turn.completed',
                            'usage': {'input_tokens': 10, 'output_tokens': 3}})
                    return subprocess.CompletedProcess(argv, 0, stdout=out, stderr='')

                with patch('run_codex.ROOT', root), patch('run_codex.check_start', return_value={}), \
                     patch('run_codex.reserve_start'), patch('run_experiment.check_start', return_value={}), \
                     patch('run_codex.os.getuid', return_value=1000, create=True), \
                     patch('run_codex.os.getgid', return_value=1000, create=True), \
                     patch('subprocess.run', side_effect=docker), patch('run_codex.time.sleep'):
                    result = execute_diagnostic(distribution, config, root / 'run', root / 'unused-auth')
                self.assertEqual(result['end_reason'], expected)
                self.assertTrue(result['processes_stopped'])
                self.assertTrue(result['submission_fixed'])
                usage = read(root / 'run/usage.json')
                self.assertEqual(usage['usage_complete'], case in ('success', 'error'))
                self.assertEqual(usage['total_tokens'], 13 if case in ('success', 'error') else None)
                preservation = read(root / 'run/preservation.json')
                self.assertTrue(preservation['restore_verified'])
                verify_receipt(archive, preservation['receipt'])
                restored = root / 'restored' / preservation['reference']['package_id']
                self.assertEqual(read(restored / 'usage.json'), usage)
                self.assertEqual(read(restored / 'manifest.json')['phase'], 'diagnostic')
                if case != 'setup':
                    self.assertTrue(any(c[:2] == ['docker', 'stop'] for c in commands))


if __name__ == '__main__':
    unittest.main()

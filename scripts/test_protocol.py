import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from normalize_usage import normalize
from prepare_workspace import prepare, validate_pair
from run_experiment import run, snapshot, verify_snapshot
from model_gateway import validate_request
from gateway_usage import collect


def event(identity='1', session='parent', mode='request', usage=None, **extra):
    return dict(run_id='run', session_id=session, event_id=identity, request_id=identity,
                mode=mode, usage=usage if usage is not None else {'input_tokens': 10, 'output_tokens': 3}, **extra)


class UsageTests(unittest.TestCase):
    def test_gateway_policy(self):
        body = {'model':'fixed','reasoning':{'effort':'xhigh'},'stream':True,'tools':[{'type':'function'}]}
        validate_request(body, 'fixed', 'xhigh')
        for field, value in [('tools',[{'type':'web_search'}]),('model','other'),
                             ('input',[{'image_url':'https://github.com/private'}])]:
            with self.assertRaises(ValueError):
                validate_request(dict(body, **{field:value}), 'fixed', 'xhigh')

    def test_gateway_interrupted_request(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            e=event(session='implementation')
            e['usage']=None
            (root/'started.jsonl').write_text(json.dumps(e)+'\n',encoding='utf-8')
            self.assertFalse(collect(root)['usage_complete'])

    def test_duplicate_cache_reasoning_not_added(self):
        e = event(usage={'input_tokens': 10, 'output_tokens': 3,
                         'input_tokens_details': {'cached_tokens': 5},
                         'output_tokens_details': {'reasoning_tokens': 2}})
        self.assertEqual(normalize([e, e], ['parent'], True)['total_tokens'], 13)

    def test_cumulative(self):
        events = [event(mode='cumulative'), event('2', mode='cumulative', usage={'input_tokens': 20, 'output_tokens': 8})]
        self.assertEqual(normalize(events, ['parent'], True)['total_tokens'], 28)

    def test_child_retry(self):
        result = normalize([event(), event('2', session='child'), event('3', status='failed')], ['parent', 'child'], True)
        self.assertEqual(result['total_tokens'], 39)
        self.assertEqual(result['observed_request_count'], 3)

    def test_missing(self):
        e = event()
        e['usage'] = None
        result = normalize([e], ['parent', 'child'], True)
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['total_tokens'])

    def test_inventory_unknown(self):
        self.assertIsNone(normalize([event()], ['parent'])['total_tokens'])

    def test_parent_inclusive_rejected(self):
        with self.assertRaises(ValueError):
            normalize([event(includes_children=True)], ['parent'], True)

    def test_duplicate_request(self):
        a, b = event(), event('2')
        b['request_id'] = a['request_id']
        self.assertEqual(normalize([a, b], ['parent'], True)['total_tokens'], 13)


class FilesTests(unittest.TestCase):
    def test_generated_symlink_excluded_but_source_link_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'node_modules').mkdir()
            (root/'source.py').write_text('source',encoding='utf-8')
            try:
                (root/'node_modules/tool').symlink_to(root/'source.py')
            except OSError:
                self.skipTest('Platform does not permit symlinks')
            self.assertEqual(set(snapshot(root)), {'source.py'})
            (root/'source-link.py').symlink_to(root/'source.py')
            with self.assertRaises(ValueError):
                snapshot(root)

    def test_real_pair(self):
        validate_pair(Path(__file__).resolve().parents[1])

    def test_allowlist_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for condition in ('normal', 'anti'):
                (root / condition).mkdir()
            (root / 'docs').mkdir()
            normal = '冒頭100万円\n承認者: 999,999円以下\n承認者: 1,000,000円以上'
            (root / 'normal/spec.md').write_text(normal, encoding='utf-8')
            (root / 'anti/spec.md').write_text(normal.replace('999,999', '499,999').replace('1,000,000', '500,000'), encoding='utf-8')
            (root / 'implementation_prompt.md').write_text('common', encoding='utf-8')
            (root / 'AGENTS.md').write_text('CANARY', encoding='utf-8')
            manifest = prepare(root, 'normal', root / 'distribution')
            self.assertEqual(set(manifest['files']), {'spec.md', 'RUN_CONTRACT.md'})
            workspace = root / 'distribution/workspace'
            original = snapshot(workspace)
            (workspace / 'new.txt').write_text('changed', encoding='utf-8')
            with self.assertRaises(ValueError):
                verify_snapshot(workspace, original)
            (root / 'anti/spec.md').write_text('unexpected', encoding='utf-8')
            with self.assertRaises(ValueError):
                validate_pair(root)

    def test_environment_failure_freezes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'distribution/workspace').mkdir(parents=True)
            (root / 'distribution/workspace/spec.md').write_text('spec', encoding='utf-8')
            write = {'files': {k: {'sha256': v} for k, v in snapshot(root / 'distribution/workspace').items()}}
            (root / 'distribution/distribution.json').write_text(json.dumps(write), encoding='utf-8')
            config = dict(experiment_version='test', model_id='test', effort='test', agent_version='test',
                          tool_versions={}, subagent_policy='disabled', execution_order=1,
                          environment={'image': 'test@sha256:' + 'a'*64}, command=['true'],
                          budget={'kind': 'wall_clock_seconds', 'value': 1, 'scope': 'container'})
            with patch('run_experiment.subprocess.run', side_effect=OSError('unavailable')):
                result = run(root / 'distribution', config, root / 'run')
            self.assertEqual(result['end_reason'], 'environment_failure')
            self.assertTrue(result['submission_fixed'])
            self.assertTrue((root / 'run/frozen/spec.md').exists())

    def test_only_worker_wait_timeout_counts_as_budget_exhausted(self):
        for stage in ('create', 'start', 'wait'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as d:
                root=Path(d)
                workspace=root/'distribution/workspace';workspace.mkdir(parents=True)
                (workspace/'spec.md').write_text('spec',encoding='utf-8')
                manifest={'files':{k:{'sha256':v} for k,v in snapshot(workspace).items()}}
                (root/'distribution/distribution.json').write_text(json.dumps(manifest),encoding='utf-8')
                config=dict(experiment_version='test',model_id='test',effort='test',agent_version='test',
                            tool_versions={},subagent_policy='disabled',execution_order=1,
                            environment={'image':'sha256:'+'a'*64},command=['true'],
                            budget={'kind':'wall_clock_seconds','value':3600,'scope':'container'})
                def command(args,**kwargs):
                    if args[1]==stage:raise subprocess.TimeoutExpired(args,kwargs.get('timeout',30))
                    stdout='false\n' if args[1]=='inspect' else ''
                    return subprocess.CompletedProcess(args,0,stdout=stdout,stderr='')
                with patch('run_experiment.subprocess.run',side_effect=command):
                    result=run(root/'distribution',config,root/'run')
                self.assertEqual(result['end_reason'],'budget_exhausted' if stage=='wait' else 'environment_failure')
                self.assertEqual(result['timeout_stage'],stage)
                self.assertTrue(result['submission_fixed'])
                self.assertEqual(result['management']['version'],'measurement-control-v2')
                for filename,digest in result['management']['files'].items():
                    import hashlib
                    self.assertEqual(hashlib.sha256((root/'run/management-source'/filename).read_bytes()).hexdigest(),digest)


if __name__ == '__main__':
    unittest.main()

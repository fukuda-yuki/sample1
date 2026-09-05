"""No Docker calls: verify that aborted/error collection cannot delete usage originals."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gateway_usage import collect
from run_codex import execute, save_usage


def request(identity='a', usage=None):
    return {'run_id':'run','session_id':'implementation','event_id':identity,'request_id':identity,
            'mode':'request','usage':usage,'model_id':'model','provider':'provider'}


def originals(root, *, complete=True):
    start=request()
    (root/'started.jsonl').write_text(json.dumps(start)+'\n',encoding='utf-8')
    if complete:
        final=request(usage={'input_tokens':10,'output_tokens':3})
        (root/'events.jsonl').write_text(json.dumps(final)+'\n',encoding='utf-8')


class UsageRetentionTests(unittest.TestCase):
    def setUp(self):
        patcher=patch('run_codex.check_start',return_value={'scope_sha256':'synthetic'})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ('run_codex.reserve_start', 'run_codex.validate_distribution', 'preservation_gate.preserve_finished'):
            mocked=patch(name);mocked.start();self.addCleanup(mocked.stop)
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_partial_json_keeps_known_usage_but_never_claims_complete(self):
        originals(self.root)
        with (self.root/'events.jsonl').open('a',encoding='utf-8') as stream:stream.write('{"event_id":')
        result=collect(self.root)
        self.assertFalse(result['usage_complete'])
        self.assertIsNone(result['total_tokens'])
        self.assertEqual(result['observed_tokens'],13)
        self.assertTrue(any(m['reason']=='malformed_raw_usage' for m in result['missing']))

    def test_identity_mismatch_and_conflict_do_not_make_false_totals(self):
        for mutation in ('request_id','duplicate','negative'):
            with self.subTest(mutation=mutation):
                originals(self.root)
                final=request(usage={'input_tokens':10,'output_tokens':3})
                if mutation=='request_id':final['request_id']='different-request'
                if mutation=='negative':final['usage']['input_tokens']=-10
                if mutation=='duplicate':
                    other=copy.deepcopy(final);other['usage']['output_tokens']=20
                    text=json.dumps(final)+'\n'+json.dumps(other)+'\n'
                else:text=json.dumps(final)+'\n'
                (self.root/'events.jsonl').write_text(text,encoding='utf-8')
                result=collect(self.root)
                self.assertFalse(result['usage_complete'])
                self.assertIsNone(result['total_tokens'])

    def test_unconfirmed_producer_and_copy_failure_retain_raw(self):
        raw=self.root/'raw';raw.mkdir();originals(raw)
        output=self.root/'run';output.mkdir()
        with patch('run_codex.shutil.copytree',side_effect=PermissionError()):
            save_usage(output,raw,producer_stopped=False)
        summary=json.loads((output/'usage.json').read_text())
        self.assertEqual(summary['observed_tokens'],13)
        self.assertIsNone(summary['total_tokens'])
        self.assertTrue((raw/'events.jsonl').exists())
        self.assertEqual({m['reason'] for m in summary['missing']},{'raw_usage_copy_error','gateway_stop_unconfirmed'})

    def test_drain_exception_and_keyboard_interrupt_always_save_evidence(self):
        for failure in (ValueError('broken collector'),KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                output=self.root/type(failure).__name__
                def fake_run(distribution,config,target,**kwargs):
                    target.mkdir()
                    originals(Path(config['usage_raw_directory']))
                    manifest={'end_reason':'agent_completed','usage_raw_directory':config['usage_raw_directory']}
                    (target/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
                    return manifest
                calls=0
                def flaky_collect(raw):
                    nonlocal calls
                    calls+=1
                    if calls==1:raise failure
                    return collect(raw)
                with patch('run_codex.os.getuid',return_value=1000,create=True),patch('run_codex.os.getgid',return_value=1000,create=True),patch('run_codex.subprocess.run',return_value=subprocess.CompletedProcess([],0)),patch('run_codex.run',side_effect=fake_run),patch('run_codex.time.sleep'),patch('run_codex.collect',side_effect=flaky_collect):
                    with self.assertRaises(type(failure)):
                        execute(self.root,{'model_id':'model','effort':'xhigh','environment':{}},output,self.root/'unused-auth')
                summary=json.loads((output/'usage.json').read_text())
                self.assertIsNone(summary['total_tokens'])
                self.assertFalse(summary['usage_complete'])
                self.assertEqual(summary['observed_tokens'],13)
                self.assertTrue((Path(summary['raw_directory'])/'events.jsonl').exists())
                self.assertTrue((output/'raw-usage/events.jsonl').exists())

    def test_success_keeps_raw_and_completed_total(self):
        raw=self.root/'raw';raw.mkdir();originals(raw)
        output=self.root/'run';output.mkdir()
        save_usage(output,raw,producer_stopped=True)
        summary=json.loads((output/'usage.json').read_text())
        self.assertTrue(summary['usage_complete'])
        self.assertEqual(summary['total_tokens'],13)
        self.assertEqual((raw/'events.jsonl').read_bytes(),(output/'raw-usage/events.jsonl').read_bytes())

    def test_setup_failure_preserves_stage_and_stderr_without_argv(self):
        output=self.root/'setup-failure'
        captured=[]
        def fake_run(distribution,config,target,**kwargs):
            captured.append(config)
            target.mkdir()
            (target/'manifest.json').write_text(json.dumps(config))
            return {'end_reason':'environment_failure'}
        def command(argv,**kwargs):
            if argv[:2]==['docker','start']:
                raise subprocess.CalledProcessError(1,argv,stderr=b'docker0 missing')
            return subprocess.CompletedProcess(argv,0)
        with patch('run_codex.os.getuid',return_value=1000,create=True),patch('run_codex.os.getgid',return_value=1000,create=True),patch('run_codex.subprocess.run',side_effect=command),patch('run_codex.run',side_effect=fake_run):
            execute(self.root,{'model_id':'model','effort':'xhigh','environment':{}},output,self.root/'auth-path')
        detail=captured[0]['setup_failure_detail']
        self.assertEqual(detail,{'type':'CalledProcessError','stage':['docker','start'],'stderr':'docker0 missing'})
        self.assertFalse(json.loads((output/'usage.json').read_text())['usage_complete'])

    def test_successful_wrapper_stops_gateway_before_final_snapshot(self):
        output=self.root/'wrapper-run'
        commands=[]
        def fake_command(command,**kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command,0)
        def fake_run(distribution,config,target,**kwargs):
            self.assertFalse(target.exists())
            target.mkdir();originals(Path(config['usage_raw_directory']))
            return {'end_reason':'agent_completed'}
        with patch('run_codex.os.getuid',return_value=1000,create=True),patch('run_codex.os.getgid',return_value=1000,create=True),patch('run_codex.subprocess.run',side_effect=fake_command),patch('run_codex.run',side_effect=fake_run),patch('run_codex.time.sleep'):
            result=execute(self.root,{'model_id':'model','effort':'xhigh','environment':{}},output,self.root/'unused-auth')
        self.assertEqual(result['end_reason'],'agent_completed')
        summary=json.loads((output/'usage.json').read_text())
        self.assertEqual(summary['total_tokens'],13)
        self.assertTrue(summary['producer_stopped'])
        self.assertTrue(Path(summary['raw_directory']).is_absolute())
        self.assertTrue(any(c[:3]==['docker','stop','--time'] for c in commands))
        self.assertTrue(any(c[:3]==['docker','rm','-f'] for c in commands))


if __name__=='__main__':unittest.main()

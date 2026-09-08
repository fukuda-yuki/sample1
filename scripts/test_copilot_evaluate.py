"""Synthetic subprocess boundary test; not a real private E2E execution."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch
from copilot_batch import evaluate_run,ROOT
from test_telemetry_link import fixture
from telemetry_link import atomic
from preserve import read,digest


class EvaluationTests(unittest.TestCase):
    def test_separate_attempt_binding_registration_and_archive(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'run';rid,_=fixture(run)
            atomic(run/'usage.json',{'usage_complete':True,'total_tokens':27,'observed_tokens':27})
            m=read(run/'manifest.json');m['environment']={'image':'sha256:'+'a'*64};atomic(run/'manifest.json',m)
            private=root/'private';private.mkdir()
            (private/'run.mjs').write_text('synthetic; never executed')
            (private/'package-lock.json').write_text('{}')
            atomic(private/'case-manifest.json',read(ROOT/'evaluation/case-manifest.json'))
            eid=str(uuid.uuid4());result=private/eid/'result';result.mkdir(parents=True)
            (result/'evaluator-snapshot').mkdir()
            (result/'evaluator-snapshot/requirements-ledger.json').write_bytes((ROOT/'evaluation/requirements-ledger.json').read_bytes())
            ledger=read(ROOT/'evaluation/requirements-ledger.json');submission=digest(run/'snapshot.json')
            rows=[{'run_id':rid,'evaluation_id':i['evaluation_id'],'case_id':case,'status':'blocked',
                   'score_version':'fixture-v1','submission_hash':submission} for i in ledger['items']
                   for case in (('lower','upper') if i['evaluation_id']=='T-006-05' else ('main',))]
            (result/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            atomic(result/'summary.json',{'run_id':rid,'kind':'evaluation','submission_hash':submission,
                   'evaluator_hash':'fixture-v1','ledger_hash':digest(ROOT/'evaluation/requirements-ledger.json'),
                   'outcome':'server_unavailable','quality':0,
                   'counts':{'denominator':57,'pass':0,'fail':0,'blocked':57,'error':0}})
            validity=private/'evaluation-validity.json';atomic(validity,{'schema_version':1,'attempts':[]})
            scope=root/'scope.json';atomic(scope,{'preservation':{'archive':{'windows':str(root/'archive'),'linux':str(root/'archive')}}})
            config={'score_version':'fixture-v1','evaluator_files':{'run.mjs':digest(private/'run.mjs')},'authorization_file':str(scope)}
            resources={'evaluation_id':eid,'output':str(result),'researcher_container':'synthetic-research',
                       'app_container':'synthetic-app','network':'synthetic-network'}
            def command(args,**kwargs):return subprocess.CompletedProcess(args,0,json.dumps(resources),'')
            with patch('copilot_batch.subprocess.run',side_effect=command):
                answer=evaluate_run(root,config,{'run_id':rid},run,private,'sha256:'+'b'*64,validity)
            self.assertTrue(answer['valid'])  # Valid zero score does not stop the experiment.
            self.assertEqual(read(validity)['attempts'][0]['status'],'valid')
            self.assertEqual(read(run/'evaluation-ref.json')['submission_hash'],submission)
            self.assertTrue((run/'evaluation-preservation.json').exists())
            self.assertEqual(digest(run/'snapshot.json'),submission)

if __name__=='__main__':unittest.main()

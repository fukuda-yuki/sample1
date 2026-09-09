from pathlib import Path
import unittest
from verification_plan import plan
from preserve import digest
ENV={k:'test-fixture' for k in ['worker_image','evaluator_image','browser_version','node_version','python_version','contract_sha256','execution_config_sha256']}

class Selection(unittest.TestCase):
    def test_only_identical_complete_receipts_reused(self):
        root=Path(__file__).resolve().parents[1];first=plan(root,[],environment=ENV)
        receipt=dict(first['checks'][0],passed=True,checks=first['checks'][0]['required_checks'],evidence='test-only',evidence_refs=[{'path':'README.md','sha256':digest(root/'README.md')}])
        again=plan(root,[receipt],environment=ENV);self.assertEqual(again['checks'][0]['action'],'reuse')
        receipt['fingerprints']['files']['scripts/run_copilot.py']='changed'
        self.assertEqual(plan(root,[receipt],environment=ENV)['checks'][0]['action'],'run')
    def test_environment_change_invalidates_evidence(self):
        root=Path(__file__).resolve().parents[1];r=plan(root,[])['checks'][0]
        r.update(passed=True,checks=r['required_checks'])
        self.assertEqual(plan(root,[r],environment={'image':'new'})['checks'][0]['action'],'run')

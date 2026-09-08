"""In-memory evidence format fixtures only; no real acceptance is registered."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import copilot_scope as scope
from preserve import read, digest
from telemetry_link import atomic


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = read(Path(__file__).resolve().parents[1] / 'config/copilot-example.json')
        self.source.update(experiment_id='70075fed-73b9-4fda-8705-221e4df0d157',
            phase='copilot-validation', planned_run='normal-001', condition='normal',
            model_id='muse-spark-1.3-contributor-free', synthetic=False,
            authorization_file=str(self.root/'scope.json'),
            budget={'kind':'wall_clock_seconds','scope':'container','value':3600},
            environment={'image':'sha256:'+'a'*64}, score_version='score-pinned',
            evaluator_files={'run.mjs':'a'*64}, input_hashes={k:'b'*64 for k in scope.INPUTS})
        self.target = dict(self.source, experiment_id='70075fed-73b9-4fda-8705-221e4df0d158',
                           experiment_version='copilot-comparison-002', phase='comparison')
        self.evidence = dict(schema_version=1, kind='real-copilot-muse', synthetic=False,
            source_config=self.source, source_experiment=scope.experiment_identity(self.source),
            settings_sha256=scope.settings_hash(self.source), file_edit=True, tool_execution=True,
            model_continuation=True, usage_reconciled=True, monitor_readback=True,
            independent_evaluation=True, preservation_verified=True)
        # This successful-path document is never written/registered as real evidence.
        self.path = self.root/'format-fixture.json'; self.path.write_text('format fixture only')
        self.reference = dict(path=self.path.name, sha256=digest(self.path),
                              target_experiment=scope.experiment_identity(self.target))

    def check(self, target=None, evidence=None, reference=None):
        with patch('copilot_scope.read', return_value=evidence or self.evidence):
            return scope.check_acceptance(target or self.target, reference or self.reference, self.root)

    def test_different_identity_compatible_but_start_hash_unchanged(self):
        self.assertNotEqual(scope.settings_hash(self.source), scope.settings_hash(self.target))
        self.assertEqual(scope.acceptance_conditions(self.source), scope.acceptance_conditions(self.target))
        result = self.check()
        self.assertEqual(result['source_experiment'], scope.experiment_identity(self.source))
        self.assertEqual(result['target_experiment'], scope.experiment_identity(self.target))
        atomic(self.root/'scope.json', {'settings_sha256':scope.settings_hash(self.source)})
        with self.assertRaisesRegex(ValueError, 'authorization settings mismatch'):
            scope.check(self.target)

    def test_every_execution_condition_change_rejected(self):
        for key in scope.COMPATIBLE:
            with self.subTest(key=key):
                changed=copy.deepcopy(self.target)
                if key=='budget': changed[key]['value'] += 1
                elif key=='environment': changed[key]['image']='sha256:'+'c'*64
                elif key=='input_hashes': changed[key][scope.INPUTS[0]]='c'*64
                elif key=='evaluator_files': changed[key]['run.mjs']='c'*64
                elif key=='tool_versions': changed[key]={'node':'different'}
                else: changed[key]='different'
                with self.assertRaises(ValueError): self.check(target=changed)

    def test_comparison_gate_retains_bindings_without_consuming_start(self):
        authority=dict(settings_sha256=scope.settings_hash(self.target),allowed_starts=['normal-001'],
                       account_terms_confirmed=True,exact_model_confirmed=True,live_acceptance=self.reference)
        atomic(self.root/'scope.json',{'fixture':True})
        def document(path):
            return authority if Path(path).name=='scope.json' else self.evidence
        with patch('copilot_scope.read',side_effect=document), patch('preservation_gate.check_restoration') as guard:
            result=scope.check(self.target)
            self.assertEqual(result['acceptance']['source_experiment'],scope.experiment_identity(self.source))
            guard.assert_called_once()
        self.assertFalse((self.root/'starts').exists())

    def test_missing_evidence_pins_and_flags_rejected(self):
        for key in ('source_config','source_experiment','settings_sha256','kind','synthetic',
                    'file_edit','tool_execution','model_continuation','usage_reconciled',
                    'monitor_readback','independent_evaluation','preservation_verified'):
            with self.subTest(key=key):
                evidence=copy.deepcopy(self.evidence); del evidence[key]
                with self.assertRaises((ValueError, KeyError)): self.check(evidence=evidence)
        for key in scope.COMPATIBLE:
            changed=copy.deepcopy(self.target); del changed[key]
            with self.assertRaises((ValueError, KeyError, TypeError)): self.check(target=changed)
        for key in ('input_hashes','evaluator_files','score_version'):
            changed=copy.deepcopy(self.target); changed[key]={} if key!='score_version' else None
            with self.assertRaises(ValueError): self.check(target=changed)

    def test_modified_file_wrong_binding_and_synthetic_rejected(self):
        self.path.write_text('modified')
        with self.assertRaisesRegex(ValueError,'hash mismatch'): self.check()
        self.reference['sha256']=digest(self.path)
        for key, value in [('synthetic',True),('kind','synthetic'),('settings_sha256','bad'),
                           ('source_experiment',scope.experiment_identity(self.target))]:
            with self.assertRaises(ValueError): self.check(evidence=dict(self.evidence,**{key:value}))
        with self.assertRaises(ValueError):
            self.check(reference=dict(self.reference,target_experiment=scope.experiment_identity(self.source)))
        self.path.unlink()
        with self.assertRaises(FileNotFoundError): self.check()


if __name__=='__main__': unittest.main()

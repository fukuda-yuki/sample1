import copy
import json
from pathlib import Path
import tempfile
import unittest
from measurement import summarize
from validity import apply_case_adjudications,digest


class Measurement(unittest.TestCase):
    def test_legacy_reach_is_unknown_and_pair_keeps_one_id(self):
        rows=[dict(evaluation_id='T-006-05',case_id=c,status='pass') for c in ['lower','upper']]
        result=summarize(rows,attempted=True,validity='invalid')
        f=result['features']['F-006']
        self.assertEqual((f['target_ids'],f['raw_pass_ids'],f['unknown']),(1,1,2))
        self.assertEqual(f['business_assertion_reached'],0)
        self.assertIsNone(f['effective_quality_percent'])

    def test_prerequisite_blocked_is_not_direct_business_verification(self):
        rows=[dict(evaluation_id='T-009-01',case_id='main',status='blocked',evidence={'measurement':{'cause':'target_discovery','prerequisite':['ログイン'],'business_assertion_reached':False}})]
        f=summarize(rows,attempted=True)['features']['F-009']
        self.assertEqual((f['prerequisite_blocked'],f['business_assertion_reached']),(1,0))

    def test_adjudication_is_derived_and_unobserved_cause_rejected(self):
        row=dict(evaluation_id='T-009-01',case_id='main',status='fail',evidence={'measurement':{'events':[{'sequence':7}],'business_assertion_reached':False}})
        original=copy.deepcopy(row)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);file=root/'decision.json'
            decision=dict(evaluation_id='T-009-01',case_id='main',responsibility='implementation',reason='Observed inaccessible prerequisite',root_event=7)
            document={'kind':'case-causality-adjudication','evaluator_hash':'version','cases':[decision]}
            file.write_text(json.dumps(document))
            record={'evaluator_hash':'version','adjudications':[{'path':'decision.json','sha256':digest(file)}]}
            derived=apply_case_adjudications([row],record,root/'registry.json')
            self.assertEqual(row,original);self.assertEqual(derived[0]['status'],'fail')
            self.assertEqual(summarize(derived)['responsibilities'],{'implementation':1})
            decision['root_event']=999;file.write_text(json.dumps(document))
            with self.assertRaises(ValueError):apply_case_adjudications([row],record,root/'registry.json')

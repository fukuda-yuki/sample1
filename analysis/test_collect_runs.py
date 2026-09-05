"""Collector integration tests use the private evaluator's real 58-case JSON shape."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from aggregate import aggregate, write_outputs
from collect_runs import collect
from test_aggregate import LEDGER, fixture


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = self.root / 'ledger.json'
        save(self.ledger, LEDGER)
        self.ledger_hash = hashlib.sha256(self.ledger.read_bytes()).hexdigest()

    def build(self, name='run-1', status='pass', outcome='completed', complete=True):
        run_dir, eval_dir = self.root / name, self.root / (name + '-evaluation-001')
        run_dir.mkdir(); eval_dir.mkdir()
        save(run_dir / 'manifest.json', dict(run_id=name, phase='pilot', distribution={'condition':'normal'},
                                            experiment_version='v1', end_reason='agent_completed'))
        save(run_dir / 'usage.json', dict(usage_complete=complete, total_tokens=100 if complete else None,
                                         observed_tokens=100 if complete else 60))
        save(run_dir / 'snapshot.json', {'README.md':'frozen-file-hash'})
        submission = hashlib.sha256((run_dir / 'snapshot.json').read_bytes()).hexdigest()
        rows = fixture()[1]
        for row in rows:
            row.update(run_id=name, submission_hash=submission, score_version='eval-v1', status=status,
                       evidence={'title':row['evaluation_id'],'message':None,'attachments':[],'duration_ms':10})
        summary = dict(schema_version=1, kind='evaluation', run_id=name, submission_hash=submission,
                       evaluator_hash='eval-v1', ledger_hash=self.ledger_hash, browser_version='145',
                       started_at='2026-09-05T00:00:00Z', finished_at='2026-09-05T00:01:00Z',
                       outcome=outcome, error=None,
                       quality=None if outcome in ('evaluator_error','isolation_blocked') else (1 if status=='pass' else 0),
                       counts={'denominator':57, **{s:57 if s==status else 0 for s in ('pass','fail','blocked','error')}},
                       diagnostic_counts={'pass':5,'fail':0,'blocked':0,'error':0})
        self.save_report(eval_dir, summary, rows)
        return {'run_directory':str(run_dir),'evaluation_directory':str(eval_dir)}, summary, rows

    def save_report(self, directory, summary, rows):
        save(directory / 'summary.json', summary)
        (directory / 'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n', encoding='utf-8')

    def test_58_cases_become_57_ids_and_csv_preserves_provenance(self):
        selected, _, rows = self.build()
        self.assertEqual(len(rows), 58)
        runs, results = collect([selected], self.ledger)
        aggregated, details = aggregate(runs, results, LEDGER)
        self.assertEqual((aggregated[0]['passed'],aggregated[0]['quality_percent'],len(details)),(57,100,57))
        out=self.root/'output';write_outputs(aggregated,details,out)
        with (out/'runs.csv').open(encoding='utf-8-sig',newline='') as stream:
            row=next(csv.DictReader(stream))
        self.assertEqual(row['evaluation_attempt'],str(Path(selected['evaluation_directory']).resolve()))
        self.assertEqual(row['ledger_hash'],self.ledger_hash)
        self.assertEqual(len(row['results_hash']),64)

    def test_partial_case_and_missing_usage_remain_distinct(self):
        selected, summary, rows = self.build(complete=False)
        next(r for r in rows if r['case_id']=='upper')['status']='fail'
        summary.update(quality=56/57, counts={'denominator':57,'pass':56,'fail':1,'blocked':0,'error':0})
        self.save_report(Path(selected['evaluation_directory']),summary,rows)
        runs,results=collect([selected],self.ledger)
        result=aggregate(runs,results,LEDGER)[0][0]
        self.assertIsNone(result['total_tokens'])
        self.assertEqual(result['observed_tokens'],60)
        self.assertAlmostEqual(result['quality_percent'],100*56/57)

    def test_pre_snapshot_evaluator_failure_is_retained_with_null_quality(self):
        selected,summary,rows=self.build(status='error',outcome='evaluator_error')
        summary.update(submission_hash=None,error='browserType.launch failed before snapshot')
        for row in rows:row['submission_hash']=None
        self.save_report(Path(selected['evaluation_directory']),summary,rows)
        runs,results=collect([selected],self.ledger)
        result=aggregate(runs,results,LEDGER)[0][0]
        self.assertIsNone(result['quality_percent'])
        self.assertIsNone(result['submission_hash'])
        self.assertEqual(result['errors'],57)

    def test_explicit_missing_evaluation_and_other_runs_are_preserved(self):
        selected,_,_=self.build()
        missing,_,_=self.build('run-2')
        missing['evaluation_directory']=None
        runs,results=collect([selected,missing],self.ledger)
        rows,_=aggregate(runs,results,LEDGER)
        self.assertEqual([r['run_id'] for r in rows],['run-1','run-2'])
        self.assertEqual(rows[0]['quality_percent'],100)
        self.assertIsNone(rows[1]['quality_percent'])
        self.assertEqual(rows[1]['evaluation_error'],'No evaluation selected')

    def test_reject_wrong_ledger_snapshot_summary_and_truncation(self):
        for mutation in ('ledger','snapshot','counts','quality','truncated','duplicate','version','unknown_case'):
            with self.subTest(mutation=mutation):
                selected,summary,rows=self.build('run-'+mutation)
                if mutation=='ledger':summary['ledger_hash']='other'
                if mutation=='snapshot':summary['submission_hash']='other'
                if mutation=='counts':summary['counts']['pass']=56
                if mutation=='quality':summary['quality']=0
                if mutation=='truncated':rows.pop()
                if mutation=='duplicate':rows[-1]=copy.deepcopy(rows[0])
                if mutation=='version':rows[0]['score_version']='other'
                if mutation=='unknown_case':rows[0]['case_id']='unexpected'
                self.save_report(Path(selected['evaluation_directory']),summary,rows)
                with self.assertRaises(ValueError):collect([selected],self.ledger)

    def test_duplicate_run_attempts_are_rejected_and_inputs_unchanged(self):
        selected,_,_=self.build()
        files=list(self.root.rglob('*.json'))+list(self.root.rglob('*.jsonl'))
        before={p:p.read_bytes() for p in files}
        runs,results=collect([selected,selected],self.ledger)
        with self.assertRaises(ValueError):aggregate(runs,results,LEDGER)
        self.assertEqual(before,{p:p.read_bytes() for p in files})


if __name__=='__main__':
    unittest.main()

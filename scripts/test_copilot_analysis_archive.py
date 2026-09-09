"""Portable synthetic originals tests; no model, monitor or private E2E invocation."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from copilot_batch import plan, load, export, ROOT
from copilot_analysis_archive import preserve_analysis, restore_analysis
from check_copilot_analysis_restore import check
from preserve import read, digest
from telemetry_link import atomic, canonical
from gateway_usage import collect
from test_telemetry_link import fixture


def originals(source):
    plan(source/'batch', {'synthetic':True,'phase':'copilot-validation',
         'experiment_version':'copilot-synthetic-validation'},123)
    config,index=load(source/'batch')
    private=source/'private-synthetic-eval';private.mkdir()
    records=[]
    for n,slot in enumerate(index['runs']):
        run=source/'batch/runs'/slot['planned_run']/'attempt'
        rid,_=fixture(run,experiment_id=config['experiment_id']);eid=str(uuid.uuid4())
        slot.update(run_id=rid,evaluation_id=eid,status='completed')
        manifest=read(run/'manifest.json');manifest.update(phase='copilot-validation',
            experiment_version=config['experiment_version'],distribution={'condition':slot['condition']})
        atomic(run/'manifest.json',manifest)
        atomic(run/'usage.json',dict(usage_complete=n==0,total_tokens=27 if n==0 else None,observed_tokens=27))
        atomic(run/'telemetry-link.json',dict(run_id=rid,submission_hash=digest(run/'snapshot.json'),
            native_sha256=digest(run/'telemetry/native.jsonl'),gateway_usage_hash=canonical(collect(run/'raw-usage')),
            usage_complete=n==0,status='readback_verified' if n==0 else 'missing',
            model_calls=[{'tokens':[21,6]}]))
        directory=private/eid;directory.mkdir()
        submission=digest(run/'snapshot.json');ledger=ROOT/'evaluation/requirements-ledger.json'
        cases=[dict(run_id=rid,evaluation_id=i['evaluation_id'],case_id=c,status='pass' if n else 'fail',
                    score_version='synthetic',submission_hash=submission)
               for i in read(ledger)['items'] for c in (('lower','upper') if i['evaluation_id']=='T-006-05' else ('main',))]
        (directory/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in cases))
        atomic(directory/'summary.json',dict(kind='evaluation',run_id=rid,submission_hash=submission,
            evaluator_hash='synthetic',ledger_hash=digest(ledger),outcome='completed',quality=n,
            counts={'denominator':57,'pass':57*n,'fail':57*(1-n),'blocked':0,'error':0}))
        atomic(run/'evaluation-ref.json',dict(run_id=rid,evaluation_id=eid,submission_hash=submission,
            evaluation_directory=str(directory),summary_sha256=digest(directory/'summary.json'),
            results_sha256=digest(directory/'results.jsonl')))
        records.append(dict(evaluation_id=eid,run_id=rid,status='valid',reason='Synthetic format fixture only',
            submission_hash=submission,evaluator_hash='synthetic',summary_hash=digest(directory/'summary.json'),
            results_hash=digest(directory/'results.jsonl'),adjudications=[]))
    atomic(source/'batch/run-index.json',index)
    atomic(private/'validity.json',dict(schema_version=1,attempts=records))


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source'
        originals(self.source)
        self.batch=self.source/'batch';self.validity=self.source/'private-synthetic-eval/validity.json'

    def test_original_unavailable_csv_sqlite_and_missingness(self):
        evidence=check(self.source,self.root/'drill')
        self.assertTrue(evidence['csv_identical'])
        self.assertTrue(evidence['sqlite_all_tables_logically_identical'])
        self.assertEqual(evidence['counts']['evaluated'],2)
        self.assertEqual(evidence['counts']['usage_complete'],1)

    def test_missing_fixed_source_keeps_raw_but_suppresses_effective_score(self):
        import csv
        slot=load(self.batch)[1]['runs'][0]
        run=self.batch/'runs'/slot['planned_run']/'attempt'
        registry_before=digest(self.validity)
        (run/'frozen').rename(run/'retained-source')
        result=export(self.batch,self.validity,output=self.root/'export-missing')
        with (self.root/'export-missing/runs.csv').open(encoding='utf-8-sig',newline='') as stream:
            row=next(r for r in csv.DictReader(stream) if r['run_id']==slot['run_id'])
        self.assertEqual(row['quality_percent'],'');self.assertEqual(row['measurement_state'],'unavailable')
        self.assertEqual(row['evaluation_validity'],'valid');self.assertEqual(row['source_availability'],'missing')
        self.assertEqual(row['failed'],'57');self.assertEqual(result['evaluation_unavailable'],1)
        self.assertEqual(digest(self.validity),registry_before)

    def test_registry_adjudication_and_legacy_binding_survive_relocation(self):
        registry=read(self.validity);record=registry['attempts'][0]
        base='evaluations/'+record['evaluation_id']+'/'
        adjudication=self.validity.parent/(base+'adjudication.json')
        config=self.validity.parent/(base+'researcher-config.json')
        adjudication.parent.mkdir(parents=True)
        atomic(adjudication,{'evaluation_id':record['evaluation_id'],'outcome':'confirmed'})
        atomic(config,{'run_id':record['run_id']})
        record['adjudications']=[{'path':base+'adjudication.json','sha256':digest(adjudication)}]
        record['legacy_adjudication_binding']={'config_path':base+'researcher-config.json',
                                               'config_sha256':digest(config)}
        atomic(self.validity,registry)
        evidence=check(self.source,self.root/'drill')
        self.assertTrue(evidence['csv_identical'])
        self.assertTrue(evidence['sqlite_all_tables_logically_identical'])
        self.assertTrue(evidence['source_reads_denied'])
        config.write_text('changed')
        with self.assertRaisesRegex(ValueError,'dependency original changed'):
            preserve_analysis(self.batch,self.validity,self.root/'rejected-archive')

    def test_wrong_selected_id_submission_and_evaluation_pair_rejected(self):
        slots=load(self.batch)[1]['runs']
        first=self.batch/'runs'/slots[0]['planned_run']/'attempt/evaluation-ref.json'
        second=read(self.batch/'runs'/slots[1]['planned_run']/'attempt/evaluation-ref.json')
        ref=read(first)
        for change in ({'evaluation_id':'wrong'},{'submission_hash':'wrong'},
                       {'evaluation_directory':second['evaluation_directory']},
                       {'evaluation_id':second['evaluation_id'],'evaluation_directory':second['evaluation_directory'],
                        'summary_sha256':second['summary_sha256'],'results_sha256':second['results_sha256']}):
            with self.subTest(change=change):
                atomic(first,dict(ref,**change))
                with self.assertRaises(ValueError): export(self.batch,self.validity,output=self.root/'rejected')
        atomic(first,ref)

    def test_restored_original_tamper_missing_and_wrong_map_rejected(self):
        reference=preserve_analysis(self.batch,self.validity,self.root/'archive')
        destination=self.root/'restored'
        mapping=restore_analysis(self.root/'archive',reference,destination)
        payload=destination/'payload'
        def regenerate():
            return export(payload/'batch',payload/'validity.json',restoration_map=mapping)
        for file in (payload/'validity.json',payload/'evaluation-locations.json',
                     next((payload/'evaluations').glob('*/summary.json')),
                     next((payload/'batch/runs').glob('*/attempt/usage.json')),
                     next((payload/'batch/runs').glob('*/attempt/frozen/probe.txt')),
                     payload/'inputs/normal/spec.md'):
            content=file.read_bytes()
            file.write_bytes(content+b' ')
            with self.assertRaisesRegex(ValueError,'originals changed'): regenerate()
            file.unlink()
            with self.assertRaisesRegex(ValueError,'originals changed'): regenerate()
            file.write_bytes(content)
        package=destination/'package.json';content=package.read_bytes();package.write_bytes(content+b' ')
        with self.assertRaisesRegex(ValueError,'index changed'): regenerate()
        package.write_bytes(content)
        with self.assertRaisesRegex(ValueError,'root/validity mismatch'):
            export(payload/'batch',self.validity,restoration_map=mapping)
        with self.assertRaisesRegex(ValueError,'must not modify'):
            export(payload/'batch',payload/'validity.json',restoration_map=mapping,output=payload/'export')
        regenerate()


if __name__=='__main__': unittest.main()

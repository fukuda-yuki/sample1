"""Forty synthetic CLI/usage/E2E-shaped fixtures; never a real quality result."""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from copilot_batch import plan, advance, export, lock, status
from telemetry_link import link, atomic
from preserve import read, digest, pack, restore, verify

ROOT=Path(__file__).resolve().parents[1]


def main(output,command,validation=False):
    output=output.resolve()
    config={'experiment_version':'copilot-synthetic-40','model_id':'muse-fixture-contributor-free',
            'agent_version':'fake-cli','synthetic':True}
    if validation:config.update(phase='copilot-validation',experiment_version='copilot-synthetic-validation')
    count=2 if validation else 40
    first_count=1 if validation else 7
    plan(output/'batch',config,123)
    batch=output/'batch'
    private=output/'private-synthetic-eval';private.mkdir()
    registry=private/'validity.json';atomic(registry,{'schema_version':1,'attempts':[]})
    locator={'instance_id':'synthetic-40','database_path':str(output/'monitor.db'),'import_command':command}
    invocations=[]
    def runner(root,c,row,run):
        # Separate fake CLI process, no model SDK/credentials/upstream configured.
        subprocess.run([sys.executable,'-c',
            'from pathlib import Path; from test_telemetry_link import fixture; import sys; fixture(Path(sys.argv[1]),sys.argv[2],sys.argv[3])',
            str(run),row['run_id'],c['experiment_id']],cwd=ROOT/'scripts',check=True,capture_output=True)
        m=read(run/'manifest.json')
        m.update(phase=c.get('phase','comparison'),distribution={'condition':row['condition']},condition=row['condition'],experiment_version=c['experiment_version'])
        atomic(run/'manifest.json',m)
        link(run,locator,ingest=True,initialize=not Path(locator['database_path']).exists())
        receipt=pack(output/'archive','run-'+row['run_id'],{n:run/n for n in
                     ('manifest.json','snapshot.json','frozen','telemetry','telemetry-link.json','raw-usage','usage.json')},
                     metadata={'kind':'synthetic-no-model'})
        verify(output/'archive',receipt['package_id'],receipt['sha256'])
        restore(output/'archive',receipt,output/'restored'/row['run_id'])
        atomic(run/'preservation.json',receipt)
        invocations.append(row['run_id'])
    def evaluator(root,c,row,run):
        import uuid
        eid=str(uuid.uuid4());directory=private/eid;directory.mkdir()
        submission=digest(run/'snapshot.json')
        # Public 58-case output shape; this is not an execution of hidden E2E.
        ledger=read(ROOT/'evaluation/requirements-ledger.json')
        passed=row['execution_order']%2==0
        state='pass' if passed else 'fail'
        cases=[{'run_id':row['run_id'],'evaluation_id':i['evaluation_id'],'case_id':case,
                'status':state,'score_version':'synthetic-e2e-v1','submission_hash':submission}
               for i in ledger['items'] for case in (('lower','upper') if i['evaluation_id']=='T-006-05' else ('main',))]
        (directory/'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in cases))
        summary={'kind':'evaluation','run_id':row['run_id'],'submission_hash':submission,
                 'evaluator_hash':'synthetic-e2e-v1','ledger_hash':digest(ROOT/'evaluation/requirements-ledger.json'),
                 'outcome':'completed','counts':{'denominator':57,'pass':57 if passed else 0,
                                                'fail':0 if passed else 57,'blocked':0,'error':0},'quality':1 if passed else 0}
        atomic(directory/'summary.json',summary)
        data=read(registry)
        data['attempts'].append({'evaluation_id':eid,'run_id':row['run_id'],'status':'valid','reason':'Synthetic shape fixture only',
             'submission_hash':submission,'evaluator_hash':'synthetic-e2e-v1','summary_hash':digest(directory/'summary.json'),
             'results_hash':digest(directory/'results.jsonl'),'adjudications':[]})
        atomic(registry,data)
        atomic(run/'evaluation-ref.json',{'run_id':row['run_id'],'evaluation_id':eid,'submission_hash':submission,
             'evaluation_directory':str(directory),'summary_sha256':digest(directory/'summary.json'),
             'results_sha256':digest(directory/'results.jsonl')})
        return {'evaluation_id':eid,'valid':True}
    first=advance(batch,runner,evaluator,limit=first_count)
    assert first['started']==first_count
    before=list(invocations)
    with lock(batch):
        try:advance(batch,runner,evaluator)
        except FileExistsError:pass
        else:raise AssertionError('double launch allowed')
    advance(batch,runner,evaluator)
    advance(batch,runner,evaluator)
    assert len(invocations)==count and len(set(invocations))==count and invocations[:first_count]==before
    index=read(batch/'run-index.json')
    assert sum(r['condition']=='normal' for r in index['runs'])==count//2
    assert sum(r['condition']=='anti' for r in index['runs'])==count//2
    # Preserve a genuine missing observation after completing the synthetic control.
    missing=batch/'runs'/index['runs'][-1]['planned_run']/'attempt'
    original=digest(missing/'raw-usage/events.jsonl')
    with (missing/'telemetry/native.jsonl').open('a') as f:f.write('{broken')
    link(missing,locator)
    assert read(missing/'usage.json')['total_tokens'] is None
    assert digest(missing/'raw-usage/events.jsonl')==original
    one=export(batch,registry,output=output/'export-a')
    two=export(batch,registry,output=output/'export-b')
    assert one==two and one['planned']==count and one['evaluated']==count and one['plotted']==count-1
    assert one['usage_complete']==count-1
    for name in ('runs.csv','test-results.jsonl','provenance.json','tokens-quality.png'):
        assert digest(output/'export-a'/name)==digest(output/'export-b'/name),name
    for directory in ('export-a','export-b'):
        with sqlite3.connect(output/directory/'analysis.sqlite') as db:
            assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==count
            assert db.execute('SELECT count(*) FROM case_results').fetchone()[0]==count*58
            assert db.execute('SELECT sum(total_tokens) FROM runs').fetchone()[0]==(count-1)*27
    # A selected evaluation may not cross the Run/submission boundary.
    ref_path=missing/'evaluation-ref.json';reference=read(ref_path)
    atomic(ref_path,dict(reference,submission_hash='wrong'))
    try:
        export(batch,registry,output=output/'rejected-export')
        raise AssertionError('Wrong submission was joined')
    except ValueError:pass
    finally:atomic(ref_path,reference)
    evidence={'kind':'synthetic-validation-real-monitor-fake-cli-e2e-shape' if validation else 'synthetic-40-real-monitor-fake-cli-e2e-shape','model_called':False,'real_e2e':False,
              'planned':count,'normal':count//2,'anti':count//2,'unique_invocations':count,'resume_after':first_count,
              'double_launch_rejected':True,'archive_restore_count':count,'low_quality_continues':True,
              'missing_retained':True,'wrong_evaluation_rejected':True,'reexport_identical':True,'counts':one}
    atomic(output/'evidence.json',evidence)
    print(json.dumps({k:v for k,v in evidence.items() if k!='counts'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--validation',action='store_true')
    p.add_argument('import_command',nargs=argparse.REMAINDER)
    a=p.parse_args();main(a.output,a.import_command,a.validation)

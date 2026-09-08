"""Fixed 20+20 schedule, serial starts, independent evaluation and regenerable export."""
import argparse
from contextlib import contextmanager, closing
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import uuid
from preserve import read, digest, pack, restore, verify
from run_experiment import snapshot, verify_snapshot
from telemetry_link import atomic, link, canonical
from prepare_workspace import prepare
from run_copilot import execute, validate_config

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis'))
from collect_runs import collect
from aggregate import aggregate


@contextmanager
def lock(root):
    path=root/'batch.lock'
    with path.open('x') as stream:
        stream.write(json.dumps({'pid':os.getpid(),'host':__import__('socket').gethostname()}))
        stream.flush();os.fsync(stream.fileno())
    try:
        yield
    finally:
        path.unlink()


def batch_phase(config):
    phase = config.get('phase', 'comparison')
    if phase not in ('comparison', 'copilot-validation'):
        raise ValueError('Batch phase must be comparison or copilot-validation')
    return phase


def planned_count(config):
    return 2 if batch_phase(config) == 'copilot-validation' else 40


def plan(root, config, seed):
    count = planned_count(config)
    root.mkdir(parents=True,exist_ok=False)
    experiment=dict(config,experiment_id=config.get('experiment_id') or str(uuid.uuid4()),seed=seed)
    rng=random.Random(seed)
    planned=[]
    for block in range(1,count//2+1):
        pair=['normal','anti'];rng.shuffle(pair)
        for condition in pair:
            planned.append({'planned_run':f'{condition}-{block:03d}','condition':condition,
                            'repetition':block,'block':block,'execution_order':len(planned)+1})
    # Bind public inputs and execution configuration before any implementation.
    experiment['input_hashes']={p:digest(ROOT/p) for p in
        ('normal/spec.md','anti/spec.md','implementation_prompt.md','evaluation/requirements-ledger.json','evaluation/case-manifest.json')}
    atomic(root/'experiment.json',experiment)
    atomic(root/'planned-runs.json',{'experiment_id':experiment['experiment_id'],'order':planned})
    atomic(root/'run-index.json',{'experiment_id':experiment['experiment_id'],
           'plan_sha256':digest(root/'planned-runs.json'),'config_sha256':digest(root/'experiment.json'),
           'runs':[dict(p,run_id=None,status='not_started',evaluation_id=None) for p in planned]})
    for p in planned:(root/'runs'/p['planned_run']).mkdir(parents=True)
    return status(root)


def load(root):
    config,index=read(root/'experiment.json'),read(root/'run-index.json')
    if index['config_sha256']!=digest(root/'experiment.json') or index['plan_sha256']!=digest(root/'planned-runs.json'):
        raise ValueError('Fixed plan/config changed')
    for path,value in config['input_hashes'].items():
        if digest(ROOT/path)!=value:raise ValueError('Fixed public input changed: '+path)
    planned=read(root/'planned-runs.json')['order']
    if len(planned)!=planned_count(config) or len(index['runs'])!=len(planned) or any({k:r[k] for k in p}!=p for r,p in zip(index['runs'],planned)):
        raise ValueError('Planned slots differ')
    ids=[r['run_id'] for r in index['runs'] if r['run_id']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate Run UUID')
    return config,index


def status(root):
    _,index=load(root)
    counts={}
    for row in index['runs']:counts[row['status']]=counts.get(row['status'],0)+1
    missing_usage=0
    for row in index['runs']:
        if row['run_id']:
            usage=root/'runs'/row['planned_run']/'attempt/usage.json'
            if not usage.exists() or not read(usage).get('usage_complete'):missing_usage+=1
    return {'planned':len(index['runs']),'started':sum(r['run_id'] is not None for r in index['runs']),
            'states':counts,'usage_missing_or_unconfirmed':missing_usage}


def advance(root, runner, evaluator=None, *, limit=40, after_evaluation=None):
    """Callbacks are internal test seams. CLI supplies only the real guarded runner."""
    with lock(root):
        config,index=load(root)
        executed=0
        for row in index['runs']:
            run=root/'runs'/row['planned_run']/'attempt'
            if row['status']=='completed':
                verify_snapshot(run/'frozen',read(run/'snapshot.json'))
                if not read(run/'usage.json')['usage_complete']:
                    row['status']='missing';atomic(root/'run-index.json',index);break
                continue
            if row['status']!='not_started':
                # Never reimplement an uncertain/failed start. Recover fixed original only.
                if run.exists() and (run/'manifest.json').exists():
                    m=read(run/'manifest.json')
                    if m['run_id']!=row['run_id']:raise ValueError('Manifest UUID mismatch')
                    if m.get('processes_stopped') and m.get('submission_fixed'):
                        verify_snapshot(run/'frozen',read(run/'snapshot.json'))
                        if row['status']=='running':row['status']='awaiting_evaluation'
                atomic(root/'run-index.json',index)
                break
            if executed>=limit:break
            row.update(run_id=str(uuid.uuid4()),status='running')
            atomic(root/'run-index.json',index)  # UUID exists before CLI/provider/telemetry.
            try:
                runner(root,config,row,run)
                m=read(run/'manifest.json')
                if m.get('phase')!=batch_phase(config):raise ValueError('Run phase differs from fixed batch')
                if m['run_id']!=row['run_id'] or not m.get('processes_stopped') or not m.get('submission_fixed'):
                    raise ValueError('Run identity/stop/freeze not established')
                verify_snapshot(run/'frozen',read(run/'snapshot.json'))
                row['status']='frozen'
                atomic(root/'run-index.json',index)
                if not read(run/'usage.json')['usage_complete']:
                    row['status']='missing';break
                row['status']='awaiting_evaluation'
                atomic(root/'run-index.json',index)
                if evaluator is None:break
                evaluation=evaluator(root,config,row,run)
                row['evaluation_id']=evaluation['evaluation_id']
                row['status']='completed' if evaluation['valid'] else 'failed'
                atomic(root/'run-index.json',index)
                if after_evaluation is not None:after_evaluation(root)
                if not evaluation['valid']:break
                executed+=1
            except (Exception, KeyboardInterrupt) as error:
                row.update(status='failed',failure=type(error).__name__)
                atomic(root/'run-index.json',index)
                raise
            finally:
                atomic(root/'run-index.json',index)
    return status(root)


def real_runner(secret,opt_in,locator):
    def start(root,config,row,run):
        c=dict(config,**{k:row[k] for k in ('planned_run','condition','execution_order')},phase=batch_phase(config))
        distribution=run.parent/'distribution'
        prepare(ROOT,row['condition'],distribution)
        execute(distribution,c,run,secret,opt_in=opt_in,run_id=row['run_id'])
        link(run,locator,ingest=True)
        from preservation_gate import archive_root
        archive=archive_root(read(Path(c['authorization_file'])))
        receipt=pack(archive,'linked-'+row['run_id'],{n:run/n for n in
                     ('manifest.json','snapshot.json','frozen','telemetry','telemetry-link.json','raw-usage','usage.json')},
                     metadata={'kind':'copilot-linked-run','run_id':row['run_id']})
        verify(archive,receipt['package_id'],receipt['sha256'])
        restored=restore(archive,receipt,run.parent/'restored-linked')
        atomic(run/'linked-restoration.json',restored)
        atomic(run/'linked-preservation.json',receipt)
    return start


def evaluate_run(root,config,row,run,private_root,image,validity):
    """Only independent researcher containers see private tests; never resume worker."""
    if config.get('synthetic'):
        raise ValueError('Synthetic batches cannot invoke the real evaluator entry')
    m=read(run/'manifest.json')
    if not m.get('processes_stopped') or not m.get('submission_fixed'):
        raise ValueError('Stop and freeze implementation first')
    before=digest(run/'snapshot.json')
    verify_snapshot(run/'frozen',read(run/'snapshot.json'))
    if not (private_root/'run.mjs').is_file() or not (private_root/'package-lock.json').is_file():
        raise ValueError('Private evaluator or dependency lock missing')
    expected=config.get('evaluator_files')
    if not expected or not config.get('score_version'):
        raise ValueError('Pin the actual calibrated evaluator file hashes and score_version in the plan')
    for name,value in expected.items():
        if digest(private_root/name)!=value:raise ValueError('Evaluator version changed')
    if read(private_root/'case-manifest.json')!=read(ROOT/'evaluation/case-manifest.json'):
        raise ValueError('Fixed 58-case definition differs')
    helper=subprocess.run([sys.executable,str(ROOT/'evaluation/prepare-app-container.py'),str(run.resolve()),
             str(private_root.resolve()),'--evaluator-image',image],check=True,capture_output=True,text=True,timeout=180)
    resources=json.loads(helper.stdout)
    try:
        subprocess.run(['docker','start','-a',resources['researcher_container']],
                       capture_output=True,timeout=1800)
    finally:
        for name in (resources['app_container'],resources['researcher_container']):
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=30)
        subprocess.run(['docker','network','rm',resources['network']],capture_output=True,timeout=30)
        if digest(run/'snapshot.json')!=before:raise ValueError('Snapshot changed during evaluation')
        verify_snapshot(run/'frozen',read(run/'snapshot.json'))
    result=Path(resources['output'])
    selection={'run_directory':str(run.resolve()),'evaluation_directory':str(result.resolve())}
    summary=read(result/'summary.json')
    if summary['evaluator_hash']!=config['score_version']:raise ValueError('Wrong evaluator score version')
    ledger=result/'evaluator-snapshot/requirements-ledger.json'
    collect([selection],ledger,validity_path=validity,validation=batch_phase(config)=='copilot-validation')  # Validate all 58 raw cases/counts/hashes before registration.
    # Register only this new, pinned independent attempt; never replace an adjudication.
    registry_lock=validity.with_suffix(validity.suffix+'.lock')
    with registry_lock.open('x') as guard:guard.write(resources['evaluation_id'])
    try:
        registry=read(validity)
        if not any(r['evaluation_id']==resources['evaluation_id'] for r in registry['attempts']):
            registry['attempts'].append({'evaluation_id':resources['evaluation_id'],'run_id':row['run_id'],
                'status':'valid' if summary['outcome'] in ('completed','server_unavailable') else 'pending',
                'reason':'Pinned independent evaluator; infrastructure failures remain pending',
                'submission_hash':summary['submission_hash'],'evaluator_hash':summary['evaluator_hash'],
                'summary_hash':digest(result/'summary.json'),'results_hash':digest(result/'results.jsonl'),'adjudications':[]})
            atomic(validity,registry)
    finally:registry_lock.unlink()
    runs,results=collect([selection],ledger,validity_path=validity,validation=batch_phase(config)=='copilot-validation')
    rows,_=aggregate(runs,results,read(ledger),validation=batch_phase(config)=='copilot-validation')
    reference={'run_id':row['run_id'],'submission_hash':before,'evaluation_id':resources['evaluation_id'],
               'evaluation_directory':str(result.resolve()),'summary_sha256':digest(result/'summary.json'),
               'results_sha256':digest(result/'results.jsonl'),'score_version':read(result/'summary.json')['evaluator_hash']}
    # Keep prior attempts; selection changes are explicit, never overwrite the originals.
    refs=run/'evaluation-refs';refs.mkdir(exist_ok=True)
    atomic(refs/(resources['evaluation_id']+'.json'),reference)
    atomic(run/'evaluation-ref.json',reference)
    from preservation_gate import archive_root
    archive=archive_root(read(Path(config['authorization_file'])))
    receipt=pack(archive,'evaluation-'+resources['evaluation_id'],
                 {'result':result,'evaluation-ref.json':run/'evaluation-ref.json','evaluation-validity.json':validity},
                 metadata={'kind':'independent-evaluation','run_id':row['run_id']})
    verify(archive,receipt['package_id'],receipt['sha256'])
    restored=restore(archive,receipt,run.parent/('restored-evaluation-'+resources['evaluation_id']))
    atomic(run/'evaluation-restoration.json',restored)
    atomic(run/'evaluation-preservation.json',receipt)
    return {'evaluation_id':resources['evaluation_id'],'valid':rows[0]['quality_percent'] is not None and read(run/'usage.json')['usage_complete']}


def export(root,validity,*,output=None):
    config,index=load(root)
    output=output or root/'export'
    if (output/'provenance.json').exists():
        previous=read(output/'provenance.json')
        if (previous.get('phase','comparison')!=batch_phase(config)
                or previous.get('experiment_id')!=config['experiment_id']):
            raise ValueError('Export directory belongs to a different phase or experiment')
    selections=[]; links={}; ledgers=[]
    for slot in index['runs']:
        if slot['run_id'] is None:continue
        run=root/'runs'/slot['planned_run']/'attempt'
        if not (run/'manifest.json').exists() or not (run/'usage.json').exists():continue
        manifest=read(run/'manifest.json')
        if manifest['run_id']!=slot['run_id']:raise ValueError('Wrong Run in slot')
        if manifest['phase']!=batch_phase(config):raise ValueError('Run phase differs from fixed batch')
        if (run/'frozen').exists():verify_snapshot(run/'frozen',read(run/'snapshot.json'))
        ref=read(run/'evaluation-ref.json') if (run/'evaluation-ref.json').exists() else None
        if ref:
            if ref['run_id']!=slot['run_id'] or ref['submission_hash']!=digest(run/'snapshot.json'):
                raise ValueError('Selected evaluation identity mismatch')
            directory=Path(ref['evaluation_directory'])
            if digest(directory/'summary.json')!=ref['summary_sha256'] or digest(directory/'results.jsonl')!=ref['results_sha256']:
                raise ValueError('Selected evaluation original changed')
            if not config.get('synthetic') and read(directory/'summary.json')['evaluator_hash']!=config.get('score_version'):
                raise ValueError('Selected evaluation uses an unplanned score version')
            ledger=directory/'evaluator-snapshot/requirements-ledger.json'
            if ledger.exists():ledgers.append(ledger)
        telemetry=read(run/'telemetry-link.json') if (run/'telemetry-link.json').exists() else {}
        if telemetry.get('run_id')!=slot['run_id'] or telemetry.get('submission_hash')!=digest(run/'snapshot.json'):
            raise ValueError('Telemetry/submission identity mismatch')
        if telemetry.get('native_sha256')!=digest(run/'telemetry/native.jsonl'):
            raise ValueError('Native spool changed after reconciliation')
        from gateway_usage import collect as gateway_collect
        if telemetry.get('gateway_usage_hash')!=canonical(gateway_collect(run/'raw-usage')):
            raise ValueError('Gateway originals changed after reconciliation')
        current_usage=read(run/'usage.json')
        if current_usage.get('usage_complete') and telemetry.get('usage_complete'):
            if current_usage['total_tokens']!=sum(sum(c['tokens']) for c in telemetry['model_calls']):
                raise ValueError('Usage and linked call totals disagree')
        links[slot['run_id']]=telemetry
        selections.append({'run_directory':str(run),'evaluation_directory':ref['evaluation_directory'] if ref else None})
    if selections:
        ledger=ledgers[0] if ledgers else ROOT/'evaluation/requirements-ledger.json'
        if any(digest(p)!=digest(ledger) for p in ledgers):raise ValueError('Mixed evaluator ledgers')
        runs,cases=collect(selections,ledger,validity_path=validity,validation=batch_phase(config)=='copilot-validation')
        for r in runs:
            t=links[r['run_id']]
            if not t.get('usage_complete') or t.get('status')!='readback_verified':
                r.update(usage_complete=False,total_tokens=None)
        rows,details=aggregate(runs,cases,read(ledger),validation=batch_phase(config)=='copilot-validation')
    else:rows,details,cases=[],[],[]
    by_id={r['run_id']:r for r in rows}
    output.mkdir(parents=True,exist_ok=True)
    public=[]
    for slot in index['runs']:
        row=by_id.get(slot['run_id'],{'run_id':slot['run_id'], 'phase':batch_phase(config), 'condition':slot['condition'],
                 'experiment_version':config['experiment_version'],'score_version':None,'submission_hash':None,
                 'end_reason':'environment_failure','total_tokens':None,'observed_tokens':None,'usage_complete':False,
                 'denominator':57,'passed':None,'failed':None,'blocked':None,'errors':None,'quality_percent':None,
                 'missing_reason':slot['status']})
        row=dict(row,planned_run=slot['planned_run'],state=slot['status'],model_id=config.get('model_id'),
                 agent_version=config.get('agent_version'))
        # Do not export private evaluator paths/evidence, only immutable identifiers/hashes.
        row.pop('evaluation_attempt',None)
        row.pop('validity_reason',None)
        row.pop('evaluation_error',None)
        if row.get('quality_percent') is None:row['missing_reason']='usage or independent evaluation unavailable'
        calls=links.get(slot['run_id'],{}).get('model_calls',[])
        row['input_tokens']=sum(c['tokens'][0] for c in calls) if row['usage_complete'] else None
        row['output_tokens']=sum(c['tokens'][1] for c in calls) if row['usage_complete'] else None
        public.append(row)
    fields=sorted(set().union(*(r.keys() for r in public)))
    public=[{k:r.get(k) for k in fields} for r in public]
    for name,values in [('runs.csv',public),('missing-runs.csv',[r for r in public if r['total_tokens'] is None or r['quality_percent'] is None])]:
        with (output/name).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(values)
    safe_cases=[{k:r[k] for k in ('run_id','evaluation_id','case_id','status','score_version','submission_hash')} for r in cases]
    (output/'test-results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in safe_cases),encoding='utf-8')
    provenance={'experiment_id':config['experiment_id'],'synthetic':config.get('synthetic',False),
                'input_hashes':config['input_hashes'],'planned':len(index['runs']),'phase':batch_phase(config),'started':sum(s['run_id'] is not None for s in index['runs']),
                'not_started':sum(s['run_id'] is None for s in index['runs']),
                'evaluated':sum(r['quality_percent'] is not None for r in public),
                'usage_complete':sum(r['usage_complete'] for r in public),
                'plotted':sum(r['total_tokens'] is not None and r['quality_percent'] is not None for r in public),
                'code_hashes':{p:digest(ROOT/p) for p in ('scripts/copilot_batch.py','scripts/telemetry_link.py',
                              'analysis/collect_runs.py','analysis/aggregate.py','analysis/plot.py')},
                'telemetry_refs':[{k:t.get(k) for k in ('run_id','native_sha256','otlp_sha256','session_ids','trace_ids','submission_hash')}
                                  for t in links.values()]}
    for reference,t in zip(provenance['telemetry_refs'],links.values()):
        reference['monitor_instance']=t.get('monitor',{}).get('instance_id')
        reference['monitor_build_hashes']=list(t.get('monitor',{}).get('build_files_sha256',{}).values())
        reference['monitor_schema']=t.get('ingestion',{}).get('schema')
        reference['ingestion_records']=t.get('ingestion',{}).get('records')
    atomic(output/'provenance.json',provenance)
    temp=output/'analysis.sqlite.tmp'
    if temp.exists():temp.unlink()
    with closing(sqlite3.connect(temp)) as db:
        db.execute('CREATE TABLE runs(planned_run TEXT PRIMARY KEY,run_id TEXT UNIQUE,row_json TEXT NOT NULL,total_tokens INTEGER,quality_percent REAL)')
        db.execute('CREATE TABLE case_results(run_id TEXT,evaluation_id TEXT,case_id TEXT,status TEXT,PRIMARY KEY(run_id,evaluation_id,case_id))')
        db.execute('CREATE TABLE telemetry_refs(run_id TEXT PRIMARY KEY,reference_json TEXT NOT NULL)')
        db.execute('CREATE TABLE evaluations(run_id TEXT PRIMARY KEY,evaluation_id TEXT,score_version TEXT,submission_hash TEXT)')
        db.execute('CREATE TABLE provenance(document_json TEXT NOT NULL)')
        for r in public:db.execute('INSERT INTO runs VALUES(?,?,?,?,?)',(r['planned_run'],r['run_id'],json.dumps(r),r['total_tokens'],r['quality_percent']))
        for c in safe_cases:db.execute('INSERT INTO case_results VALUES(?,?,?,?)',tuple(c[k] for k in ('run_id','evaluation_id','case_id','status')))
        for t in provenance['telemetry_refs']:db.execute('INSERT INTO telemetry_refs VALUES(?,?)',(t['run_id'],json.dumps(t)))
        for r in public:
            if r.get('evaluation_id'):db.execute('INSERT INTO evaluations VALUES(?,?,?,?)',tuple(r.get(k) for k in ('run_id','evaluation_id','score_version','submission_hash')))
        db.execute('INSERT INTO provenance VALUES(?)',(json.dumps(provenance),))
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==len(index['runs'])
        db.commit()
    temp.replace(output/'analysis.sqlite')
    # Existing plot requires unique labels even for unstarted slots. Keep real run_id nullable in exports.
    plot_rows=[dict(r,run_id=r['run_id'] or 'unstarted:'+r['planned_run']) for r in public]
    with (output/'plot-input.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(plot_rows)
    from plot import plot
    plot(output/'plot-input.csv',output/'tokens-quality.png')
    return provenance


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['plan','check','run','status','resume','evaluate','export'])
    p.add_argument('root',type=Path)
    p.add_argument('--config',type=Path);p.add_argument('--seed',type=int,default=20260908)
    p.add_argument('--locator',type=Path);p.add_argument('--secret-file',type=Path)
    p.add_argument('--execute-real-model',action='store_true')
    p.add_argument('--private-root',type=Path);p.add_argument('--evaluator-image');p.add_argument('--validity',type=Path)
    p.add_argument('--slot');p.add_argument('--limit',type=int,default=40)
    a=p.parse_args();root=a.root.resolve()
    if a.action=='plan':
        if not a.config:p.error('plan requires --config')
        result=plan(root,read(a.config),a.seed)
    elif a.action=='status':result=status(root)
    elif a.action=='export':
        if not a.validity:p.error('export requires current --validity')
        result=export(root,a.validity)
    else:
        config,index=load(root)
        if a.action=='check':
            from execution_scope import check_start
            next_slot=next((s for s in index['runs'] if s['status']=='not_started'),None)
            if next_slot:
                c=dict(config,**{k:next_slot[k] for k in ('planned_run','condition','execution_order')},phase=batch_phase(config))
                validate_config(c);check_start(c)
            result={'model_called':False,'status':status(root)}
        elif a.action=='evaluate':
            if not all((a.slot,a.private_root,a.evaluator_image,a.validity)):p.error('evaluate requires slot/private-root/evaluator-image/validity')
            with lock(root):
                row=next(r for r in index['runs'] if r['planned_run']==a.slot)
                if not row['run_id']:p.error('slot not started')
                result=evaluate_run(root,config,row,root/'runs'/row['planned_run']/'attempt',a.private_root,a.evaluator_image,a.validity)
                row.update(evaluation_id=result['evaluation_id'],status='completed' if result['valid'] else 'failed')
                atomic(root/'run-index.json',index)
                if batch_phase(config)=='copilot-validation':export(root,a.validity)
        else:
            if config.get('synthetic'):p.error('Synthetic test batches cannot start real inference')
            if not all((a.locator,a.secret_file,a.execute_real_model)):p.error('run/resume requires locator/secret-file/execute-real-model')
            evaluator=None
            if a.private_root:
                if not all((a.evaluator_image,a.validity)):p.error('private-root requires evaluator-image/validity')
                evaluator=lambda r,c,s,d:evaluate_run(r,c,s,d,a.private_root,a.evaluator_image,a.validity)
            after=(lambda r:export(r,a.validity)) if batch_phase(config)=='copilot-validation' and evaluator else None
            result=advance(root,real_runner(a.secret_file,a.execute_real_model,read(a.locator)),evaluator,limit=a.limit,after_evaluation=after)
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as error:
        print('Stopped: '+str(error),file=sys.stderr)
        raise SystemExit(2)

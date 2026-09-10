"""Seal the approved 20+20 generation policy after non-model validation."""
import argparse
import hashlib
from pathlib import Path
import shutil
import uuid
from preserve import read,digest,write_new,pack,restore,verify,tree
from copilot_parallel import make_plan,load
from copilot_scope import settings_hash
from parallel_acquisition import POLICY,SCOPE,MODELS,assigned_config,validate_batch,verify_ready
from prepare_workspace import prepare,render_contract
from telemetry_link import atomic,link


def main(base):
    root=Path(__file__).resolve().parents[1];base=base.resolve();batch=base/'batch'
    archive=Path('/mnt/c/Users/mwam0/ResearchArchives/sample1');preflight=base/'preflight'
    old=root/'results/acquisition10-20260910/batch'
    c=read(old/'experiment.json')
    for name,h in c['input_hashes'].items():assert digest(root/name)==h,name
    c.update(experiment_id=str(uuid.uuid4()),experiment_version='copilot-acquisition20-parallel-20260911',
        repetitions_per_condition=20,max_parallel=5,acquisition_policy=POLICY,
        authorization_file=str(base/'authorization.json'),seed=20260911)
    make_plan(batch,c,20260911);c,index=load(batch);validate_batch(c,index)
    scope={'authorized_scope':SCOPE,'generation_policy':POLICY,'acquisition_root':str(batch),
        'allowed_starts':[r['planned_run'] for r in index['runs']],'do_not_start':[],
        'authority':'User requested implementation of the approved 20+20 rolling K5 acquisition and cumulative 60-run report.',
        'preservation':{'archive':{'windows':r'C:\Users\mwam0\ResearchArchives\sample1','linux':str(archive)}}}
    atomic(base/'authorization.json',scope)
    docker=read(preflight/'docker/evidence.json')
    assert docker['model_called'] is False and docker['five_plus_one_overlap'] and docker['real_cli_runs']==5
    logs=('parallel-tests.log','regression-tests.log')
    for name in logs:
        text=(preflight/name).read_text()
        assert '\nOK\n' in text and 'FAILED' not in text,name
    distributions=[]
    for cond in ('normal','anti'):
        dist=preflight/('distribution-'+cond);prepare(root,cond,dist,c)
        assert {p.name for p in (dist/'workspace').iterdir()}=={'spec.md','RUN_CONTRACT.md'}
        distributions.append(dist/'distribution.json')
    private=root.parent/'sample1-private-eval-linux'
    for name,h in c['evaluator_files'].items():assert digest(private/name)==h,name
    common=read(root/'results/go-muse12-20260909/common-reference.json')
    verify(archive,common['package_id'],common['sha256'])
    locator=read(root/'results/meaningful-20260910/acceptance-v1/monitor/locator.json')
    locator.update(instance_id='acquisition20-'+c['experiment_id'],database_path=str(base/'monitor/monitor.db'))
    atomic(base/'monitor/locator.json',locator)
    probe=link(preflight/'docker/native-0/run',locator,ingest=True,initialize=True)
    assert probe['status']=='readback_verified'
    atomic(preflight/'monitor.json',probe)
    evidence=[preflight/'docker/evidence.json',preflight/'monitor.json',*(preflight/n for n in logs),*distributions]
    evidence += [preflight/n for n in ('lifecycle.json','gateway-tests.log') if (preflight/n).exists()]
    if (preflight/'docker-503/evidence.json').exists():evidence.append(preflight/'docker-503/evidence.json')
    sources={str(p.relative_to(root)).replace('\\','/'):digest(p) for folder in ('scripts','analysis') for p in (root/folder).glob('*.py')}
    sources.update(c['input_hashes'])
    policy=root/'reports/acquisition30-cumulative-ja-v1/analysis-policy.json'
    sources[str(policy.relative_to(root))]=digest(policy)
    models={}
    for model in MODELS:
        chosen=assigned_config(batch,c,dict(index['runs'][0],model_id=model))
        models[model]={'settings_sha256':settings_hash(chosen),'contract_sha256':hashlib.sha256(render_contract(root,chosen)).hexdigest()}
    proof={'schema_version':1,'policy':POLICY,'experiment_id':c['experiment_id'],
        'input_hashes':c['input_hashes'],'plan_sha256':index['plan_sha256'],'source_hashes':sources,
        'models':models,'checks_passed':True,'model_called':False,'runtime_reference':common,
        'checks':[{ 'path':'evidence/'+str(p.relative_to(preflight)), 'sha256':digest(p)} for p in evidence],
        'measurement_scope':'Real subprocess pipeline; five actual CLI/fake-provider Runs plus isolated evaluation surrogate; no real provider load or v6 recalibration claim.'}
    write_new(base/'generation-proof.json',proof)
    files={'proof.json':base/'generation-proof.json','experiment.json':batch/'experiment.json','planned-runs.json':batch/'planned-runs.json'}
    files.update({'evidence/'+str(p.relative_to(preflight)):p for p in evidence})
    files.update({'management/'+name:root/name for name in sources})
    files.update({'evaluator/'+name:private/name for name in c['evaluator_files']})
    ref=pack(archive,'parallel-generation-readiness-'+c['experiment_id'],files,
        metadata={'kind':'generation-readiness','policy':POLICY},references=[common])
    receipt=restore(archive,ref,base/'restored-readiness')
    scope['preservation']['generation_readiness']=receipt;atomic(base/'authorization.json',scope)
    verify_ready(batch,c,index)
    atomic(base/'review/validity.json',{'schema_version':1,'attempts':[]})
    # Record hashes, not additional copies of all historical Runs.
    legacy={}
    for name in ('acquisition10-preserve-first-20260910','acquisition10-reanalysis-ja-v1','acquisition10-reanalysis-ja-v2'):
        for rel,entry in tree(root/'reports'/name).items():legacy['reports/'+name+'/'+rel]=entry['sha256']
    for row in read(old/'run-index.json')['runs']:
        run=old/'runs'/row['planned_run']/'attempt'
        for name in ('manifest.json','snapshot.json','usage.json','evaluation-ref.json'):
            legacy[str((run/name).relative_to(root))]=digest(run/name)
    write_new(base/'legacy-hashes-before.json',legacy)
    write_new(base/'ready.json',{'experiment_id':c['experiment_id'],'model_called':False,'reference':ref,'restoration':receipt,
        'planned':40,'implementation_limit':5,'evaluation_during_generation':1,'evaluation_after_generation':4})
    print('Parallel generation proof preserved and restored. 40 new slots ready; no model called.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);a=p.parse_args();main(a.base)

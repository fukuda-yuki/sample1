"""Seal a generation-only proof after actual non-model checks. No inference."""
import argparse
import hashlib
from pathlib import Path
import shutil
import uuid
from preserve import read, digest, write_new, pack, restore, verify, verify_receipt
from copilot_parallel import make_plan, load
from copilot_scope import settings_hash
from serial_acquisition import MODELS, check_generation, slot_config
from prepare_workspace import render_contract, prepare
from telemetry_link import atomic, link


def main(base):
    root=Path(__file__).resolve().parents[1];base=base.resolve()
    preflight=base/'preflight';batch=base/'batch'
    archive=Path('/mnt/c/Users/mwam0/ResearchArchives/sample1')
    c=read(root/'results/meaningful-20260910/acceptance-v4/candidate-config.json')
    c.update(experiment_id=str(uuid.uuid4()),experiment_version='copilot-acquisition10-20260910',
             phase='data-acquisition',repetitions_per_condition=10,max_parallel=1,
             authorization_file=str(base/'authorization.json'),synthetic=False)
    make_plan(batch,c,20260910);c,index=load(batch)
    scope=dict(authorized_scope='serial-generation-10-per-condition',acquisition_root=str(batch),
               allowed_starts=[r['planned_run'] for r in index['runs']],do_not_start=[],
               authority='User approved 2026-09-10 plan: 10 starts per condition, 60min, serial, fallback consumes slots',
               preservation={'archive':{'windows':r'C:\Users\mwam0\ResearchArchives\sample1','linux':str(archive)}})
    atomic(base/'authorization.json',scope)
    for condition in ('normal','anti'):
        distribution=preflight/('distribution-'+condition)
        prepare(root,condition,distribution,c)
        assert {p.name for p in (distribution/'workspace').iterdir()}=={'spec.md','RUN_CONTRACT.md'}
    native=read(preflight/'native/evidence.json')
    assert native['model_called'] is False and all(native[k] is True for k in
        ('file_edit','tool_execution','continuation','delegation_tools_absent','native_response_reconciliation'))
    assert read(preflight/'runtime.json')['npm_ci_offline'] is True
    assert read(preflight/'isolation.json')['github_egress_denied'] is True
    tests=(preflight/'tests.log').read_text()
    assert '\nOK\n' in tests and 'FAILED' not in tests
    locator=read(root/'results/meaningful-20260910/acceptance-v1/monitor/locator.json')
    locator.update(instance_id='acquisition10-'+c['experiment_id'],database_path=str(base/'monitor/monitor.db'))
    (base/'monitor').mkdir();atomic(base/'monitor/locator.json',locator)
    probe=link(preflight/'native/run',locator,ingest=True,initialize=True)
    assert probe['status']=='readback_verified' and probe['usage_complete']
    atomic(preflight/'monitor.json',probe)
    # Exact immutable runtime package, already restored in the previous campaign;
    # verify its current bytes, matching images, and the original restore receipts.
    common=read(root/'results/go-muse12-20260909/common-reference.json')
    common_data=verify(archive,common['package_id'],common['sha256'])
    common_payload=archive/'packages'/common['package_id']/'payload'
    images=read(common_payload/'runtime/images.json')
    assert c['environment']['image'] in [i['image'] for i in images]
    old_proof=read(root/'results/go-muse12-20260909/restore-verified/proof.json')
    for receipt in old_proof['receipts']:verify_receipt(archive,receipt)
    atomic(preflight/'runtime-restoration.json',dict(common=common,images=images,receipts=old_proof['receipts'],
           current_runtime_verified=True,model_called=False,scope='Runtime assets only; old start/score authority is not reused'))
    private=root.parent/'sample1-private-eval-linux'
    for name,expected in c['evaluator_files'].items():
        assert digest(private/name)==expected, name
    models={}
    for model in MODELS:
        chosen=dict(c,model_id=model,wire_api='responses' if model in MODELS[:2] else 'completions',
                    experiment_version=c['experiment_version']+'-'+model)
        models[model]={'settings_sha256':settings_hash(chosen),'contract_sha256':hashlib.sha256(render_contract(root,chosen)).hexdigest()}
    checks={'contract_isolation':['isolation.json','distribution-normal/distribution.json','distribution-anti/distribution.json'],
            'native_protocol_usage':['native/evidence.json'], 'stop_recovery':['lifecycle.json','tests.log'],
            'monitor':['monitor.json'],'runtime_restoration':['runtime.json','runtime-restoration.json'],
            'serial_budget':['tests.log']}
    sources={}
    for folder in ('scripts','analysis'):
        sources.update({str(p.relative_to(root)):digest(p) for p in (root/folder).glob('*.py')})
    sources.update(c['input_hashes'])
    proof=dict(schema_version=1,experiment_id=c['experiment_id'],models=models,input_hashes=c['input_hashes'],
               plan_sha256=index['plan_sha256'],source_hashes=sources,
               checks={k:{'passed':True,'evidence':[{'path':'evidence/'+n,'sha256':digest(preflight/n)} for n in names]} for k,names in checks.items()},
               real_model_called=False,evaluation_readiness_claimed=False,score_version=c['score_version'])
    write_new(base/'generation-proof.json',proof)
    files={'proof.json':base/'generation-proof.json','experiment.json':batch/'experiment.json','planned-runs.json':batch/'planned-runs.json'}
    for names in checks.values():
        for n in names:files['evidence/'+n]=preflight/n
    files.update({'management/'+n:root/n for n in sources})
    files.update({'evaluator/'+n:private/n for n in c['evaluator_files']})
    reference=pack(archive,'generation-readiness-'+c['experiment_id'],files,metadata={'kind':'generation-readiness'},references=[common])
    receipt=restore(archive,reference,base/'restored-readiness')
    scope['preservation']['generation_readiness']=receipt;atomic(base/'authorization.json',scope)
    check_generation(slot_config(batch,c,index['runs'][0]),scope,None)
    atomic(base/'ready.json',dict(experiment_id=c['experiment_id'],model_called=False,reference=reference,restoration=receipt,
           planned=20,max_parallel=1,dispatch_limit=1))
    print('Generation proof restored and verified; 20 slots prepared; no real model called.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);main(p.parse_args().base)

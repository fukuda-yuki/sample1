"""Capture completed batch exports and evidence indexes; never call a model/evaluator."""
from pathlib import Path
import collections
import json
import re
import shutil
import sys
import uuid

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from preserve import read,digest,write_new
from copilot_batch import export
from run_experiment import verify_snapshot


def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if digest(source)!=digest(target):raise ValueError('Frozen input differs: '+str(target))
    else:shutil.copyfile(source,target)


def threshold_candidates(run):
    snapshot=read(run/'snapshot.json');verify_snapshot(run/'frozen',snapshot)
    pattern=re.compile(r'(?<!\d)(?:500[,_]?000|499[,_]?999|1[,_]?000[,_]?000|999[,_]?999)(?!\d)|(?:50|100)\s*万円?')
    citations=[];documents=[]
    for name in snapshot:
        p=run/'frozen'/name
        if p.suffix.lower() not in ('.cs','.md','.ts','.tsx','.json'):continue
        if any(x in name for x in ('package-lock','ui-map','node_modules')) or p.name in ('spec.md','RUN_CONTRACT.md'):continue
        text=p.read_text(encoding='utf-8-sig',errors='replace')
        lines=text.splitlines()
        for i,line in enumerate(lines):
            if pattern.search(line):
                citations.append({'path':name,'sha256':digest(p),'line':i+1,'text':line.strip(),
                    'context':'\n'.join(lines[max(0,i-2):i+3])})
        if p.suffix.lower()=='.md':
            documents.append({'path':name,'sha256':digest(p),'text':text})
    return {'candidates':citations,'documents':documents,'classification_status':'requires_source_review',
            'scope':'Saved visible decision documents and fixed implementation source; not hidden model reasoning or a new runtime test.'}


def main():
    from capture_token_components import capture as capture_token_components
    base=ROOT/'results/acquisition20-20260911';batch=base/'batch'
    index=read(batch/'run-index.json');state=read(batch/'controller.json')
    if state['status']!='stopped' or any(r['status'] in ('running','reserved','collecting','evaluating') for r in index['runs']):
        raise ValueError('Finish acquisition and evaluation collection before freezing report inputs')
    source=BASE/'source';previous=ROOT/'reports/acquisition10-reanalysis-ja-v2/source'
    for p in previous.iterdir():
        if p.is_file():copy(p,source/'previous'/p.name)
    validity=base/'review/validity.json'
    export(batch,validity,output=base/'report-export')
    for name in ('analysis.sqlite','runs.csv','runs.json','summary.json'):
        p=base/'report-export'/name
        if p.exists():copy(p,source/'additional'/name)
    for name in ('experiment.json','planned-runs.json','run-index.json','pipeline-events.jsonl','controller.json'):
        copy(batch/name,source/'additional'/name)
    for name in ('ready.json','legacy-hashes-before.json','live-boundary-first-five.json'):
        if (base/name).exists():copy(base/name,source/'additional'/name)
    copy(validity,source/'additional/validity.json')
    retained=[];qualitative=[];private_index=[]
    for row in index['runs']:
        if not row['run_id']:continue
        run=batch/'runs'/row['planned_run']/'attempt'
        if not (run/'manifest.json').exists():continue
        m=read(run/'manifest.json');receipt=read(run.parent/'acquisition-completion.json') if (run.parent/'acquisition-completion.json').exists() else {}
        events=[]
        if (run/'raw-usage/events.jsonl').exists():events=[json.loads(l) for l in (run/'raw-usage/events.jsonl').read_text().splitlines() if l.strip()]
        snapshot=read(run/'snapshot.json') if (run/'snapshot.json').exists() else {}
        metadata={'planned_run':row['planned_run'],'run_id':row['run_id'],'condition':row['condition'],
            'submission_hash':digest(run/'snapshot.json') if snapshot else None,
            'raw_end_reason':m.get('end_reason'),'exit_code':m.get('exit_code'),'stop_trigger':m.get('stop_trigger'),
            'stop_method':m.get('stop_method'),'processes_stopped':m.get('processes_stopped'),'submission_fixed':m.get('submission_fixed'),
            'completion_declaration_captured':m.get('completion_declaration') is not None,
            'elapsed_seconds':m.get('elapsed_seconds'),'started_at':m.get('started_at'),'ended_at':m.get('ended_at'),
            'gateway_http':dict(collections.Counter(str(e.get('http_status')) for e in events)),
            'response_model_ids':dict(collections.Counter(str(e.get('response_model_id')) for e in events)),
            'request_count':len(events),'lockfiles':{n:h for n,h in snapshot.items() if 'lock' in Path(n).name},
            'original':read(run/'preservation.json') if (run/'preservation.json').exists() else None,
            'original_restoration':receipt.get('original_restoration'),'linked_restoration':receipt.get('linked_restoration'),
            'management_sha256':m.get('management',{}).get('files',{}),'fallback_of':row.get('fallback_of')}
        retained.append(metadata)
        if snapshot:
            qualitative.append(dict(run_id=row['run_id'],planned_run=row['planned_run'],condition=row['condition'],
                submission_hash=metadata['submission_hash'],**threshold_candidates(run)))
        ref=run/'evaluation-ref.json'
        if ref.exists():
            e=read(ref);directory=Path(e['evaluation_directory'])
            private_index.append({'run_id':row['run_id'],'evaluation_uuid':e['evaluation_id'],
                'submission_hash':e['submission_hash'],'score_version':e['score_version'],
                'summary_sha256':e['summary_sha256'],'results_sha256':e['results_sha256'],
                'preservation':read(run/'evaluation-preservation.json'),
                'restoration':read(run/'evaluation-restoration.json'),
                'private_directory':str(directory),'public_bodies_copied':False})
    for name,value in [('retention.json',{'runs':retained}),('qualitative-candidates.json',{'runs':qualitative}),
                       ('private-evidence-index.json',{'runs':private_index})]:
        write_new(source/'additional'/name,value)
    write_new(source/'token-components.json',capture_token_components())
    hashes={str(p.relative_to(BASE)):digest(p) for p in source.rglob('*') if p.is_file()}
    manifest={'schema_version':1,'analysis_id':str(uuid.uuid4()),'inputs':hashes,
        'prior_experiment_id':'dcacece4-120a-4258-bbd8-c09940dbb67c','new_experiment_id':index['experiment_id'],
        'new_model_calls_by_this_script':0,'new_evaluations_by_this_script':0}
    write_new(BASE/'source-manifest.json',manifest)
    print(json.dumps({'source_files':len(hashes),'new_retained_runs':len(retained),'new_evaluation_refs':len(private_index)}))


if __name__=='__main__':main()

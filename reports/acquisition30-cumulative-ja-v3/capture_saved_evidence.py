"""Read saved files only. Extract new CSV-failure and large-Run observations with file bindings."""
from pathlib import Path
import collections,hashlib,json,re
from analyze import BASE,read,sha,write_json,write_csv
ROOT=BASE.parents[1]

def main():
    runs=read(BASE/'data/runs.json');extra=[]
    for r in runs:
        if not r['score_available']:continue
        path=ROOT.parent/'sample1-private-eval-linux/evaluations'/r['evaluation_uuid']/'result/results.jsonl'
        content=path.read_bytes();rows=[json.loads(x) for x in content.decode().splitlines() if x.strip()]
        row=next(x for x in rows if x['evaluation_id']=='T-016-01')
        assert row['run_id']==r['run_id'] and row['submission_hash']==r['submission_hash']
        message=re.sub(r'\x1b\[[0-9;]*m','',row['evidence'].get('message',''))
        kind='unreached' if row['status']=='blocked' else 'filename_parameter_retained' if 'filename_' in message else 'other_failure'
        extra.append({'label':r['label'],'run_id':r['run_id'],'condition':r['condition'],'evaluation_uuid':r['evaluation_uuid'],
            'submission_hash':r['submission_hash'],'evaluation_id':'T-016-01','case_id':row['case_id'],'status':row['status'],
            'message_class':kind,'message_excerpt':message[:420],'path':str(path),'sha256':hashlib.sha256(content).hexdigest(),
            'line':next(i for i,line in enumerate(content.decode().splitlines(),1) if json.loads(line).get('evaluation_id')=='T-016-01')})
    # Selection is explicit: maximum recorded tokens overall, maximum scored normal, maximum anti tokens.
    selected=[max(runs,key=lambda r:r['recorded_total_tokens']),max((r for r in runs if r['condition']=='normal' and r['score_available']),key=lambda r:r['passed_ids']),
        max((r for r in runs if r['condition']=='anti'),key=lambda r:r['recorded_total_tokens'])]
    origin={x['run_id']:x for x in read(BASE/'data/provenance.json')};requests=[];request_sources=[]
    for r in selected:
        o=origin[r['run_id']];folder='acquisition10-20260910' if o['input_database']=='raw-export-a.sqlite' else 'acquisition20-20260911'
        p=ROOT/'results'/folder/'batch/runs'/o['original_label']/'attempt/raw-usage/events.jsonl'
        content=p.read_bytes();n=0;total=0
        for line_number,line in enumerate(content.decode().splitlines(),1):
            e=json.loads(line);u=e.get('usage') or {}
            if u.get('input_tokens') is None or u.get('output_tokens') is None:continue
            n+=1;t=u['input_tokens']+u['output_tokens'];total+=t
            requests.append({'label':r['label'],'run_id':r['run_id'],'recorded_request':n,'input_tokens':u['input_tokens'],'output_tokens':u['output_tokens'],
              'cached_input_tokens':(u.get('input_tokens_details') or {}).get('cached_tokens'),'total_tokens':t,'cumulative_tokens':total,
              'event_id':e['event_id'],'timestamp':e['timestamp'],'source_line':line_number})
        assert n==r['usage_requests'] and total==r['recorded_total_tokens'],(r['label'],n,total)
        request_sources.append({'label':r['label'],'run_id':r['run_id'],'path':str(p),'sha256':hashlib.sha256(content).hexdigest(),'known_requests':n,'total_tokens':total})
    fixed=[]
    # Inspect the downloader that accompanies the highest observed normal score.
    r=selected[1];o=origin[r['run_id']];frozen=ROOT/'results/acquisition20-20260911/batch/runs'/o['original_label']/'attempt/frozen'
    for p in sorted((frozen/'frontend/src').rglob('*')):
        if p.suffix not in ('.ts','.tsx','.js','.jsx'):continue
        lines=p.read_text(encoding='utf-8').splitlines()
        hits=[{'line':i,'text':line} for i,line in enumerate(lines,1) if re.search(r'content-disposition|filename|\.download\s*=',line,re.I)]
        if hits:fixed.append({'label':r['label'],'run_id':r['run_id'],'path':str(p),'sha256':sha(p),'lines':hits})
    (BASE/'evidence').mkdir(exist_ok=True)
    write_json(BASE/'evidence/csv-failure-review.json',{'cases':extra,'source_check':'Every scored Run, no new app execution or evaluator run',
        'counts':[{'condition':c,'message_class':k,'runs':v} for (c,k),v in sorted(collections.Counter((x['condition'],x['message_class']) for x in extra).items())],
        'fixed_downloader':fixed,'attribution_limit':'A matching message class is not proof of the same source defect. Source-specific attribution is restricted to the reviewed downloader.'})
    write_json(BASE/'evidence/request-sources.json',{'selection':['largest token Run','highest-score normal Run','largest anti token Run'],'sources':request_sources})
    write_csv(BASE/'data/selected-request-trajectories.csv',requests)
    print(json.dumps({'csv_messages':len(extra),'classes':collections.Counter(x['message_class'] for x in extra),'request_rows':len(requests),'selected_source_refs':fixed},ensure_ascii=False))

if __name__=='__main__':main()

"""Fresh two-condition analysis of 60 fixed Runs; acquisition scheduling is not an analysis variable."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,math,re,sqlite3
import numpy as np

BASE=Path(__file__).resolve().parent
CONDITIONS=('normal','anti')
V6='a097b9baf7bfa605cb054deac151be6ade1b88bcdcb36f6fce89685e199d3cc3'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def connect(p):
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
def clean(x):
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,np.ndarray):return x.tolist()
    raise TypeError(type(x))
def write_json(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=clean,allow_nan=False)+'\n',encoding='utf-8')
def write_csv(p,rows):
    if not rows:return
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def trimmed(a):
    a=np.sort(a,axis=-1);k=int(a.shape[-1]*.1)
    return np.mean(a[...,k:a.shape[-1]-k],axis=-1)
def describe(a):
    a=np.array(a,dtype=float)
    return dict(n=len(a),sum=float(a.sum()),mean=float(a.mean()),median=float(np.median(a)),
      q1=float(np.quantile(a,.25)),q3=float(np.quantile(a,.75)),sd=float(np.std(a,ddof=1)),
      min=float(a.min()),max=float(a.max()),trimmed_mean_10pct=float(trimmed(a)))
def ranks(a):
    a=np.asarray(a);return np.array([np.sum(a<x)+(np.sum(a==x)+1)/2 for x in a],dtype=float)
def rho(a,b):
    x,y=ranks(a),ranks(b)
    return float(np.corrcoef(x,y)[0,1]) if np.std(x) and np.std(y) else None

def build(source):
    manifest=read(BASE/'source-manifest.json')
    for name,item in manifest['inputs'].items():assert sha(source/name)==item['sha256'],name
    rich_db=connect(source/'observations.sqlite')
    rich={r['run_id']:json.loads(r['row_json']) for r in rich_db.execute('select run_id,row_json from runs')}
    rich_cases={(r['run_id'],r['test_id'],r['case_id']):r['status'] for r in rich_db.execute('select * from case_results')}
    rich_db.close()
    raw={};raw_cases=[];evaluations=[];origin=[]
    for file in ('raw-export-a.sqlite','raw-export-b.sqlite'):
        db=connect(source/file)
        for r in db.execute('select * from runs'):
            d=json.loads(r['row_json']);assert r['run_id'] not in raw;raw[r['run_id']]=d
            origin.append({'run_id':r['run_id'],'input_database':file,'original_label':r['planned_run']})
        raw_cases.extend(dict(r) for r in db.execute('select * from case_results'))
        evaluations.extend(dict(r) for r in db.execute('select * from evaluations'));db.close()
    expected={(r['evaluation_id'],r['case_id']) for r in read(source/'case-manifest.json')['cases']}
    ledger={i['evaluation_id']:i for i in read(source/'requirements-ledger.json')['items']}
    titles={fid:title.strip() for fid,title in re.findall(r'^## (F-\d{3}):?\s+(.+)$',(source/'normal-spec.md').read_text(encoding='utf-8-sig'),re.M)}
    if len(titles)!=20:
        titles={fid:title.strip() for fid,title in re.findall(r'^## (F-\d{3})[：:\s]+(.+)$',(source/'normal-spec.md').read_text(encoding='utf-8-sig'),re.M)}
    assert len(titles)==20,titles
    assert len(raw)==len(rich)==60 and len(raw_cases)==3480 and len(expected)==58 and len(ledger)==57
    assert {(r['run_id'],r['evaluation_id'],r['case_id']):r['status'] for r in raw_cases}==rich_cases
    ev={r['run_id']:r for r in evaluations};runs=[];ids=[];cases=[]
    factual=['model_id','recorded_total_tokens','source_total_tokens','source_usage_complete','evaluation_outcome','evaluation_validity',
      'effective_quality','evaluation_uuid','submission_hash','raw_end_reason','exit_code','elapsed_seconds','completion_declaration_captured',
      'static_threshold_yen','recorded_threshold_yen','explicit_conflict_recorded','business_assertion_reached','prerequisite_blocked',
      'evaluation_unresolved','reachability_unknown','recorded_input_tokens','recorded_output_tokens','recorded_cached_input_tokens','usage_requests',
      'cached_detail_requests','http_200','http_400','http_429','http_503']
    for rid in sorted(raw):
        d=raw[rid];r=rich[rid];assert ev[rid]['score_version']==V6
        assert (d['observed_tokens'],d['evaluation_id'],d['submission_hash'])==(r['recorded_total_tokens'],r['evaluation_uuid'],r['submission_hash'])
        assert (d['total_tokens'],d['usage_complete'],d['evaluation_validity'])==(r['source_total_tokens'],r['source_usage_complete'],r['evaluation_validity'])
        assert ev[rid]['evaluation_id']==r['evaluation_uuid'] and ev[rid]['submission_hash']==r['submission_hash']
        cond=d['condition'];assert cond in CONDITIONS
        row={'label':('N-' if cond=='normal' else 'A-')+rid[:6],'run_id':rid,'condition':cond,**{k:r.get(k) for k in factual}}
        rc=[x for x in raw_cases if x['run_id']==rid];assert {(x['evaluation_id'],x['case_id']) for x in rc}==expected and len(rc)==58
        available=r['evaluation_outcome']=='completed'
        assert available==r['score_available']
        points=0
        for test in sorted(ledger):
            part=[x for x in rc if x['evaluation_id']==test]
            p=int(all(x['status']=='pass' for x in part));points+=p
            status='pass' if p else ('fail' if any(x['status']=='fail' for x in part) else 'blocked' if any(x['status']=='blocked' for x in part) else 'error')
            fid='F-'+test[2:5]
            ids.append({'run_id':rid,'label':row['label'],'condition':cond,'test_id':test,'title':ledger[test]['title'],
                'feature_id':fid,'category':ledger[test]['category'],'required_cases':len(part),'raw_status':status,'source_passed':p,'passed':p if available else None})
        assert points==d['passed']==r['source_passed_ids']
        row.update(score_available=available,passed_ids=points if available else None,pass_rate=100*points/57 if available else None,source_passed_ids=points,
           source_failed_cases=sum(x['status']=='fail' for x in rc),source_blocked_cases=sum(x['status']=='blocked' for x in rc))
        assert row['recorded_input_tokens']+row['recorded_output_tokens']==row['recorded_total_tokens']
        assert row['recorded_cached_input_tokens']<=row['recorded_input_tokens'] and row['usage_requests']>0
        row['tokens_per_recorded_request']=row['recorded_total_tokens']/row['usage_requests']
        runs.append(row)
        cases.extend({'run_id':rid,'evaluation_uuid':r['evaluation_uuid'],'test_id':x['evaluation_id'],'case_id':x['case_id'],'status':x['status'],'score_available':available} for x in rc)
    assert collections.Counter(r['condition'] for r in runs)=={'normal':30,'anti':30}
    assert len({r['label'] for r in runs})==60
    return runs,ids,cases,origin,titles

def compute(runs,ids,titles):
    groups={c:[r for r in runs if r['condition']==c] for c in CONDITIONS}
    metrics=('recorded_total_tokens','passed_ids','pass_rate','usage_requests','tokens_per_recorded_request','elapsed_seconds')
    summaries=[]
    for c,rr in groups.items():
        for metric in metrics:summaries.append({'condition':c,'metric':metric,**describe([r[metric] for r in rr if r[metric] is not None])})
    rng=np.random.default_rng(20260911);bootstrap=[]
    for metric in ('recorded_total_tokens','pass_rate','usage_requests','tokens_per_recorded_request'):
        a,b=[np.array([r[metric] for r in groups[c] if r[metric] is not None],float) for c in CONDITIONS]
        ax=a[rng.integers(0,len(a),size=(20000,len(a)))];bx=b[rng.integers(0,len(b),size=(20000,len(b)))]
        for name,fun in [('mean',lambda x:np.mean(x,axis=-1)),('median',lambda x:np.median(x,axis=-1)),('trimmed_mean_10pct',trimmed)]:
            dist=fun(ax)-fun(bx);lo,hi=np.quantile(dist,[.025,.975])
            bootstrap.append({'metric':metric,'statistic':name,'normal_n':len(a),'anti_n':len(b),'normal_minus_anti':float(fun(a)-fun(b)),
              'lower':float(lo),'upper':float(hi),'resamples':20000,'seed':20260911,'unit':'Run within condition, independently resampled'})
    feature=[];item=[]
    for fid in sorted(titles):
        for c in CONDITIONS:
            ii=[x for x in ids if x['feature_id']==fid and x['condition']==c and x['passed'] is not None]
            n=len({x['run_id'] for x in ii});k=len(ii)//n
            feature.append({'feature_id':fid,'title':titles[fid],'condition':c,'runs':n,'id_count':k,'passed':sum(x['passed'] for x in ii),
                'pass_rate':100*sum(x['passed'] for x in ii)/len(ii),'failed':sum(x['raw_status']=='fail' for x in ii),'blocked':sum(x['raw_status']=='blocked' for x in ii),
                'zero_feature_runs':sum(sum(x['passed'] for x in ii if x['run_id']==rid)==0 for rid in {x['run_id'] for x in ii})})
    for test in sorted({x['test_id'] for x in ids}):
        d={'test_id':test,'feature_id':'F-'+test[2:5],'title':next(x['title'] for x in ids if x['test_id']==test)}
        for c in CONDITIONS:
            ii=[x for x in ids if x['test_id']==test and x['condition']==c and x['passed'] is not None]
            d[c+'_n']=len(ii);d[c+'_passed']=sum(x['passed'] for x in ii);d[c+'_rate']=sum(x['passed'] for x in ii)/len(ii)
            for status in ('fail','blocked','error'):d[c+'_'+status]=sum(x['raw_status']==status for x in ii)
        d['mean_ID_gap']=d['normal_rate']-d['anti_rate'];item.append(d)
    statuses=[]
    for c in CONDITIONS:
        rr=groups[c];ii=[x for x in ids if x['condition']==c and x['passed'] is not None]
        statuses.append({'condition':c,'started':len(rr),'scored':sum(r['score_available'] for r in rr),'whole_unavailable':sum(not r['score_available'] for r in rr),
            'usage_incomplete':sum(not r['source_usage_complete'] for r in rr),'total_tokens':sum(r['recorded_total_tokens'] for r in rr),
            'passed_ids':sum(x['passed'] for x in ii),'failed_ids':sum(x['raw_status']=='fail' for x in ii),'blocked_ids':sum(x['raw_status']=='blocked' for x in ii),
            'invalid':sum(r['evaluation_validity']=='invalid' for r in rr),'pending':sum(r['evaluation_validity']=='pending' for r in rr),
            'effective_quality_available':sum(r['effective_quality'] is not None for r in rr),
            **{k:sum(r[k] for r in rr if r[k] is not None) for k in ('recorded_input_tokens','recorded_output_tokens','recorded_cached_input_tokens','usage_requests','http_200','http_400','business_assertion_reached','prerequisite_blocked','evaluation_unresolved','reachability_unknown')}})
    sensitivity=[]
    variants={'all_recorded':lambda r:True,'without_largest_token_run':lambda r:r['run_id']!=max(runs,key=lambda r:r['recorded_total_tokens'])['run_id'],
      'score_available_only':lambda r:r['score_available'],'exclude_invalid_adjudication':lambda r:r['evaluation_validity']!='invalid',
      'source_usage_complete_only':lambda r:r['source_usage_complete']}
    for name,keep in variants.items():
        for c in CONDITIONS:
            rr=[r for r in groups[c] if keep(r)];ss=[r['passed_ids'] for r in rr if r['passed_ids'] is not None]
            sensitivity.append({'selection':name,'condition':c,'runs':len(rr),'scored':len(ss),'mean_tokens':float(np.mean([r['recorded_total_tokens'] for r in rr])),
               'median_tokens':float(np.median([r['recorded_total_tokens'] for r in rr])),'mean_pass_rate':float(np.mean(ss)*100/57)})
    # Scores missing for entire submissions can only be bounded, not filled in as observed data.
    bounds={}
    for c in CONDITIONS:
        rr=groups[c];s=sum(r['passed_ids'] for r in rr if r['passed_ids'] is not None);m=sum(not r['score_available'] for r in rr)
        bounds[c]={'missing':m,'mean_rate_lower':s/30/57*100,'mean_rate_upper':(s+57*m)/30/57*100}
    bounds['normal_minus_anti']={'lower':bounds['normal']['mean_rate_lower']-bounds['anti']['mean_rate_upper'],'upper':bounds['normal']['mean_rate_upper']-bounds['anti']['mean_rate_lower'],
      'interpretation':'Hypothetical range for the three missing Run scores only; no correction for evaluator validity and no imputation into the data.'}
    correlation=[]
    for c in (*CONDITIONS,'all'):
        rr=[r for r in runs if (c=='all' or r['condition']==c) and r['score_available']]
        for x in ('recorded_total_tokens','usage_requests','tokens_per_recorded_request','elapsed_seconds'):
            correlation.append({'condition':c,'x':x,'y':'passed_ids','n':len(rr),'spearman':rho([r[x] for r in rr],[r['passed_ids'] for r in rr])})
    concentration=[]
    for c,rr in groups.items():
        rr=sorted(rr,key=lambda r:r['recorded_total_tokens'],reverse=True);total=sum(r['recorded_total_tokens'] for r in rr)
        for k in (1,3,5):concentration.append({'condition':c,'top_k':k,'tokens':sum(r['recorded_total_tokens'] for r in rr[:k]),'share':sum(r['recorded_total_tokens'] for r in rr[:k])/total})
    low_tail=[]
    for c,rr in groups.items():
        for label,pred in [('0_to_19',lambda r:0<=r['passed_ids']<20),('20_to_39',lambda r:20<=r['passed_ids']<40),('40_to_57',lambda r:r['passed_ids']>=40)]:
            ss=[r for r in rr if r['score_available'] and pred(r)]
            low_tail.append({'condition':c,'score_band':label,'runs':len(ss),'tokens':sum(r['recorded_total_tokens'] for r in ss),
               'mean_reached_cases':float(np.mean([r['business_assertion_reached'] for r in ss])) if ss else None,
               'mean_blocked_cases':float(np.mean([r['source_blocked_cases'] for r in ss])) if ss else None,'labels':', '.join(r['label'] for r in ss)})
    decomposition={}
    for c,rr in groups.items():
        t=sum(r['recorded_total_tokens'] for r in rr);q=sum(r['usage_requests'] for r in rr)
        decomposition[c]={'mean_requests':q/30,'weighted_tokens_per_request':t/q,'mean_total_tokens':t/30}
    n,a=decomposition['normal'],decomposition['anti']
    decomposition['difference']={'mean_tokens':n['mean_total_tokens']-a['mean_total_tokens'],
       'request_count_component':(n['mean_requests']-a['mean_requests'])*(n['weighted_tokens_per_request']+a['weighted_tokens_per_request'])/2,
       'tokens_per_request_component':(n['weighted_tokens_per_request']-a['weighted_tokens_per_request'])*(n['mean_requests']+a['mean_requests'])/2,
       'interpretation':'Exact symmetric arithmetic decomposition, not a causal attribution.'}
    return dict(summaries=summaries,bootstrap=bootstrap,features=feature,items=item,statuses=statuses,sensitivity=sensitivity,missing_bounds=bounds,
       correlations=correlation,concentration=concentration,score_bands=low_tail,decomposition=decomposition)

def database(path,runs,ids,cases,origin,titles):
    if path.exists():path.unlink()
    db=sqlite3.connect(path)
    tables={'runs':runs,'id_results':ids,'case_results':cases,'provenance':origin,'features':[{'feature_id':k,'title':v} for k,v in titles.items()]}
    for name,rows in tables.items():
        types=[]
        for k in rows[0]:
            values=[r[k] for r in rows if r[k] is not None]
            t='INTEGER' if values and all(isinstance(x,(int,bool)) for x in values) else 'REAL' if values and all(isinstance(x,(int,float)) for x in values) else 'TEXT'
            types.append('"'+k+'" '+t)
        db.execute('create table '+name+' ('+','.join(types)+')')
        db.executemany('insert into '+name+' values ('+','.join('?' for _ in rows[0])+')',[tuple(r.values()) for r in rows])
    db.execute('create unique index unique_run on runs(run_id)');db.execute('create unique index unique_id on id_results(run_id,test_id)')
    db.execute('create unique index unique_case on case_results(run_id,test_id,case_id)');db.commit();db.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,default=BASE/'source');ap.add_argument('--output',type=Path,default=BASE/'data');a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    runs,ids,cases,origin,titles=build(a.source);result=compute(runs,ids,titles)
    database(a.output/'analysis.sqlite',runs,ids,cases,origin,titles)
    for name,rows in [('runs',runs),('id_results',ids),('case_results',cases),*[(k,v) for k,v in result.items() if isinstance(v,list)]]:write_csv(a.output/(name+'.csv'),rows)
    write_json(a.output/'runs.json',runs);write_json(a.output/'analysis.json',result);write_json(a.output/'provenance.json',origin)
    print(json.dumps({'runs':len(runs),'conditions':dict(collections.Counter(r['condition'] for r in runs)),'scored':sum(r['score_available'] for r in runs),'ids':len(ids),'cases':len(cases),'summaries':result['statuses'],'bootstrap':result['bootstrap'][:6]},ensure_ascii=False))

if __name__=='__main__':main()

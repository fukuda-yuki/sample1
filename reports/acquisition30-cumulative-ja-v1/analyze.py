"""Read-only SQLite analysis of two frozen acquisition batches. No runtime calls."""
from pathlib import Path
import argparse
import collections
import csv
import hashlib
import json
import platform
import re
import sqlite3
import statistics as st
import numpy as np

BASE=Path(__file__).resolve().parent
CONDITIONS=('normal','anti')
BATCHES=('previous','additional')
PRIMARY_MODEL='muse-spark-1.2-contributor'
V6='a097b9baf7bfa605cb054deac151be6ade1b88bcdcb36f6fce89685e199d3cc3'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def mean(values):
    values=[v for v in values if v is not None]
    return st.mean(values) if values else None
def ratio(a,b):return a/b if a is not None and b not in (None,0) else None
def describe(values):
    v=[x for x in values if x is not None]
    return dict(n=len(v),missing=len(values)-len(v),sum=sum(v) if v else None,mean=mean(v),
        median=st.median(v) if v else None,sd=st.stdev(v) if len(v)>1 else None,
        min=min(v) if v else None,max=max(v) if v else None)
def csv_out(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        out=csv.DictWriter(stream,fieldnames=fields);out.writeheader()
        for r in rows:out.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
def ranks(values):return [1+sum(y<x for y in values)+(sum(y==x for y in values)-1)/2 for x in values]
def correlation(x,y):
    if len(x)<3 or len(set(x))<2 or len(set(y))<2:return None
    return st.correlation(x,y)


def load_inputs():
    manifest=read(BASE/'source-manifest.json')
    for name,h in manifest['inputs'].items():
        if sha(BASE/name)!=h:raise ValueError('Changed input: '+name)
    policy=read(BASE/'analysis-policy.json')
    groups=policy['fixed_dependency_groups']
    dimensions={x['evaluation_id']:x for x in read(BASE/'source/previous/requirements-ledger.json')['items']}
    cases_expected={(x['evaluation_id'],x['case_id']) for x in read(BASE/'source/previous/case-manifest.json')['cases']}
    titles=dict(re.findall(r'^## (F-\d{3}): (.+)$',(BASE/'source/previous/normal-spec.md').read_text(encoding='utf-8-sig'),re.M))
    assert len(dimensions)==57 and len(cases_expected)==58 and len(titles)==20
    previous_q={x['run_id']:x for x in read(BASE/'source/previous/qualitative.json')['runs']}
    qfile=BASE/'reviews/qualitative-review.json'
    new_q={x['run_id']:x for x in read(qfile)['runs']} if qfile.exists() else {}
    component_file=BASE/'source/token-components.json'
    components={x['run_id']:x for x in read(component_file)['rows']} if component_file.exists() else {}
    runs=[];raw_cases=[];ids=[];features=[];provenance=[]
    for batch in BATCHES:
        source=BASE/'source'/batch
        db=sqlite3.connect((source/'analysis.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        db.row_factory=sqlite3.Row
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        raw=[json.loads(x[0]) for x in db.execute('SELECT row_json FROM runs')]
        cc=[dict(x) for x in db.execute('SELECT * FROM case_results ORDER BY run_id,evaluation_id,case_id')]
        db.close()
        plan=read(source/'planned-runs.json')['order'];planned={p['planned_run']:p for p in plan}
        retained={r['run_id']:r for r in read(source/'retention.json')['runs']}
        assert len(raw)==len(plan)==(20 if batch=='previous' else 40)
        for r in sorted(raw,key=lambda r:planned[r['planned_run']]['execution_order']):
            rid=r['run_id'];p=planned[r['planned_run']];meta=retained.get(rid,{})
            assert r.get('score_version') in (None,V6)
            if r.get('submission_hash'):assert r['submission_hash']==meta.get('submission_hash')
            first=min((x for x in plan if x['block']==p['block']),key=lambda x:x['execution_order'])['condition']
            q=previous_q.get(rid,{}) if batch=='previous' else new_q.get(rid,{})
            if batch=='additional' and q:
                assert q['submission_hash']==r.get('submission_hash')
            if batch=='previous':
                static=q.get('static_implementation',{}).get('threshold_yen')
                intended=q.get('recorded_intent',{}).get('threshold_yen')
                conflict=q.get('recorded_intent',{}).get('explicit_ap001_conflict_recorded')
            else:static=q.get('static_threshold_yen');intended=q.get('recorded_threshold_yen');conflict=q.get('explicit_conflict_recorded')
            component=components.get(rid,{})
            if component:
                assert component['submission_hash']==r['submission_hash']
                assert component['recorded_input_tokens']+component['recorded_output_tokens']==r['observed_tokens']
            outcome=r.get('evaluation_outcome')
            available=r.get('passed') is not None and outcome not in ('server_unavailable','evaluator_error','isolation_blocked')
            row=dict(slot_key=batch+'/'+r['planned_run'],run_id=rid,batch=batch,planned_run=r['planned_run'],
                condition=r['condition'],pair_id=p['block'],pair_key=batch+'/'+str(p['block']),
                execution_order=p['execution_order'],first_condition=first,model_id=r.get('model_id'),
                recorded_total_tokens=r.get('observed_tokens'),source_total_tokens=r.get('total_tokens'),
                source_usage_complete=r.get('usage_complete'),source_passed_ids=r.get('passed'),
                evaluation_outcome=outcome,score_available=available,
                passed_ids=r.get('passed') if available else None,
                recorded_pass_rate=100*r['passed']/57 if available else None,
                effective_quality=r.get('quality_percent'),evaluation_validity=r.get('evaluation_validity'),
                evaluation_uuid=r.get('evaluation_id'),evaluation_completed=r.get('evaluation_completed',False),
                raw_end_reason=meta.get('raw_end_reason',r.get('end_reason')),exit_code=meta.get('exit_code'),
                stop_trigger=meta.get('stop_trigger'),stop_method=meta.get('stop_method'),elapsed_seconds=meta.get('elapsed_seconds'),
                started_at=meta.get('started_at'),ended_at=meta.get('ended_at'),
                http_200=meta.get('gateway_http',{}).get('200',0) if meta else None,
                http_400=meta.get('gateway_http',{}).get('400',0) if meta else None,
                http_429=meta.get('gateway_http',{}).get('429',0) if meta else None,
                http_503=meta.get('gateway_http',{}).get('503',0) if meta else None,
                submission_hash=r.get('submission_hash'),state=r.get('state'),source_availability=r.get('source_availability'),
                static_threshold_yen=static,recorded_threshold_yen=intended,explicit_conflict_recorded=conflict,
                interpretation_review_status='retained_prior_review' if batch=='previous' else q.get('review_status','not_reviewed'),
                trace_structure_complete=r.get('trace_structure_complete'),native_calls_verified=r.get('native_calls_verified'),
                monitor_status=r.get('monitor_status'),raw_source=r)
            rc=[x for x in cc if rid is not None and x['run_id']==rid]
            if rc:
                assert len(rc)==58 and {(x['evaluation_id'],x['case_id']) for x in rc}==cases_expected
                assert len({(x['evaluation_id'],x['case_id']) for x in rc})==58
                for x in rc:
                    raw_cases.append(dict(run_id=rid,batch=batch,evaluation_uuid=row['evaluation_uuid'],test_id=x['evaluation_id'],case_id=x['case_id'],status=x['status'],score_available=available))
                total_pass=0
                for test_id in sorted(dimensions):
                    sub=[x for x in rc if x['evaluation_id']==test_id]
                    assert len(sub)==(2 if test_id=='T-006-05' else 1)
                    passed=int(all(x['status']=='pass' for x in sub));total_pass+=passed
                    group='direct_threshold' if test_id in groups['direct_threshold'] else 'downstream_threshold' if test_id in groups['downstream_threshold'] else 'other'
                    ids.append(dict(run_id=rid,batch=batch,condition=row['condition'],model_id=row['model_id'],test_id=test_id,
                        feature_id='F-'+test_id[2:5],dependency_group=group,passed=passed if available else None,source_passed=passed,required_cases=len(sub)))
                assert total_pass==row['source_passed_ids']
                pattern={('T-006-01','main'):'fail',('T-006-02','main'):'pass',('T-006-03','main'):'fail',
                         ('T-006-04','main'):'pass',('T-006-05','lower'):'fail',('T-006-05','upper'):'pass'}
                fingerprint={(x['evaluation_id'],x['case_id']):x['status'] for x in rc}
                row['saved_500k_pattern_matches']=all(fingerprint[k]==v for k,v in pattern.items()) if available else None
            else:row['saved_500k_pattern_matches']=None
            cov=json.loads(r.get('coverage_json') or '{}');cf=cov.get('features',{})
            row['business_assertion_reached']=sum(x.get('business_assertion_reached',0) for x in cf.values()) if cf else None
            row['prerequisite_blocked']=sum(x.get('prerequisite_blocked',0) for x in cf.values()) if cf else None
            row['evaluation_unresolved']=sum(x.get('evaluation_unresolved',0) for x in cf.values()) if cf else None
            row['reachability_unknown']=sum(x.get('unknown',0) for x in cf.values()) if cf else None
            row['completion_declaration_captured']=meta.get('completion_declaration_captured')
            row.update({k:component.get(k) for k in ('recorded_input_tokens','recorded_output_tokens','recorded_cached_input_tokens','usage_requests','cached_detail_requests')})
            for fid in sorted(titles):
                fi=[x for x in ids if x['run_id']==rid and x['feature_id']==fid] if rid else []
                if fi and available:
                    features.append(dict(run_id=rid,batch=batch,condition=row['condition'],model_id=row['model_id'],feature_id=fid,
                        feature_title=titles[fid],ids=len(fi),passed_ids=sum(x['passed'] for x in fi),
                        recorded_pass_rate=100*sum(x['passed'] for x in fi)/len(fi),**{k:cf.get(fid,{}).get(k) for k in ('business_assertion_reached','prerequisite_blocked','evaluation_unresolved')}))
            runs.append(row)
        provenance.append({'batch':batch,'source_database':'source/'+batch+'/analysis.sqlite','sha256':sha(source/'analysis.sqlite'),
            'planned_runs':len(raw),'raw_cases':len(cc)})
    assert len(runs)==60 and len({r['slot_key'] for r in runs})==60
    actual=[r['run_id'] for r in runs if r['run_id']]
    assert len(actual)==len(set(actual))
    return policy,runs,raw_cases,ids,features,provenance,titles


def pipeline_diagnostics():
    source=BASE/'source/additional'
    events=[json.loads(line) for line in (source/'pipeline-events.jsonl').read_text().splitlines() if line.strip()]
    state=read(source/'controller.json');implementing=set();evaluating=set();occupied=set()
    starts={};stops={};preserved={};es={};ee={};max_impl=max_eval=max_occupied=max_eval_during=0
    generation_ended=False;overlaps=0;samples=[]
    for e in events:
        kind=e['event'];rid=e.get('run_id')
        if kind=='implementation_started':
            assert rid not in starts
            starts[rid]=e['at'];implementing.add(rid);occupied.add(rid)
        elif kind=='implementation_stopped':
            implementing.discard(rid);stops[rid]=e['at']
        elif kind=='preserved_and_restored':
            occupied.discard(rid);preserved[rid]=e['at']
        elif kind=='generation_ended':generation_ended=True
        elif kind=='evaluation_started':
            assert rid not in es
            assert rid in preserved
            es[rid]=e['at'];evaluating.add(rid)
        elif kind in ('evaluation_preserved','evaluation_failed'):
            evaluating.discard(rid);ee[rid]=e['at']
        elif kind=='resource_sample':samples.append(e)
        max_impl=max(max_impl,len(implementing));max_eval=max(max_eval,len(evaluating));max_occupied=max(max_occupied,len(occupied))
        if not generation_ended:max_eval_during=max(max_eval_during,len(evaluating))
        if len(implementing)==5 and evaluating:overlaps+=1
    assert max_impl<=5 and max_occupied<=5 and max_eval_during<=1 and max_eval<=4
    ordered_starts=sorted(starts,key=starts.get)
    rolling=(starts[ordered_starts[5]]<max(preserved[r] for r in ordered_starts[:5])) if len(starts)>5 and all(r in preserved for r in ordered_starts[:5]) else None
    return dict(started=len(starts),stopped=len(stops),preserved=len(preserved),evaluation_started=len(es),evaluation_returned=len(ee),
        sixth_start_before_initial_five_all_restored=rolling,
        max_implementation_processes=max_impl,max_occupied_slots=max_occupied,max_evaluations_during_generation=max_eval_during,
        max_evaluations=max_eval,events_with_five_implementations_and_evaluation=overlaps,
        minimum_sampled_available_memory_gib=min((s['available_memory_bytes']/1024**3 for s in samples),default=None),
        resource_samples=len(samples),evaluation_paused_for_resources=state.get('evaluation_paused_for_resources'),
        acquisition_elapsed_minutes=(state['generation_ended_at']-min(starts.values()))/60 if starts and state.get('generation_ended_at') else None,
        pipeline_elapsed_minutes=(state['finished_at']-min(starts.values()))/60 if starts and state.get('finished_at') else None,
        collection_seconds=describe([preserved[r]-stops[r] for r in preserved if r in stops]),
        evaluation_seconds=describe([ee[r]-es[r] for r in ee if r in es]),stop_reason=state.get('stop_reason'))


def build(output):
    output=output.resolve();source=(BASE/'source').resolve()
    if output==source or source in output.parents:raise ValueError('Cannot overwrite frozen source')
    output.mkdir(parents=True,exist_ok=True)
    policy,runs,cases,ids,features,provenance,titles=load_inputs()
    summaries=[];group_rows=[];feature_rows=[];pairs=[];correlations=[];sensitivities=[];bootstraps=[];decomposition=[]
    for stratum in (*BATCHES,'cumulative'):
        population=[r for r in runs if stratum=='cumulative' or r['batch']==stratum]
        actual_models=sorted({r['model_id'] for r in population if r['model_id'] and r['model_id']!=PRIMARY_MODEL})
        for model in ('all',PRIMARY_MODEL,*actual_models):
            rr=[r for r in population if model=='all' or r['model_id']==model]
            for condition in CONDITIONS:
                sub=[r for r in rr if r['condition']==condition]
                tokens=describe([r['recorded_total_tokens'] for r in sub]);passed=describe([r['passed_ids'] for r in sub])
                summaries.append(dict(stratum=stratum,model=model,condition=condition,planned=len(sub),
                    started=sum(r['run_id'] is not None for r in sub),scored=sum(r['passed_ids'] is not None for r in sub),
                    evaluation_outputs=sum(r['source_passed_ids'] is not None for r in sub),
                    unavailable_scores=sum(r['source_passed_ids'] is not None and not r['score_available'] for r in sub),
                    tokens=tokens,passed_ids=passed,mean_pass_rate=100*passed['mean']/57 if passed['mean'] is not None else None,
                    tokens_per_passed_id=ratio(sum(r['recorded_total_tokens'] for r in sub if r['recorded_total_tokens'] is not None and r['passed_ids'] is not None),
                        sum(r['passed_ids'] for r in sub if r['recorded_total_tokens'] is not None and r['passed_ids'] is not None)),
                    validity=dict(collections.Counter(r['evaluation_validity'] or 'unavailable' for r in sub)),
                    usage_incomplete=sum(r['source_usage_complete'] is False for r in sub),
                    usage_completeness_unknown=sum(r['source_usage_complete'] is None for r in sub),
                    adopted_thresholds=dict(collections.Counter(str(r['static_threshold_yen']) for r in sub)),
                    explicit_conflict_records=sum(r['explicit_conflict_recorded'] is True for r in sub),
                    threshold_pattern_matches=sum(r['saved_500k_pattern_matches'] is True for r in sub)))
                selected={r['run_id'] for r in sub if r['run_id']}
                for group in ('direct_threshold','downstream_threshold','other'):
                    ii=[x for x in ids if x['run_id'] in selected and x['dependency_group']==group and x['passed'] is not None]
                    n=len({x['run_id'] for x in ii})
                    group_rows.append(dict(stratum=stratum,model=model,condition=condition,group=group,n=n,
                        passed=sum(x['passed'] for x in ii),ids=len(ii),mean_passed_ids=ratio(sum(x['passed'] for x in ii),n),
                        pass_rate=100*sum(x['passed'] for x in ii)/len(ii) if ii else None))
                for fid in titles:
                    ff=[x for x in features if x['run_id'] in selected and x['feature_id']==fid]
                    feature_rows.append(dict(stratum=stratum,model=model,condition=condition,feature_id=fid,title=titles[fid],n=len(ff),
                        ids_per_run=ff[0]['ids'] if ff else None,mean_pass_rate=mean([x['recorded_pass_rate'] for x in ff])))
        primary=[r for r in population if r['model_id']==PRIMARY_MODEL]
        for condition in ('all',*CONDITIONS):
            sub=[r for r in primary if (condition=='all' or r['condition']==condition) and r['recorded_total_tokens'] is not None and r['passed_ids'] is not None]
            x=[r['recorded_total_tokens'] for r in sub];y=[r['passed_ids'] for r in sub]
            correlations.append(dict(stratum=stratum,condition=condition,n=len(sub),pearson=correlation(x,y),spearman=correlation(ranks(x),ranks(y))))
        proc=[]
        for condition in CONDITIONS:
            sub=[r for r in primary if r['condition']==condition and r['recorded_total_tokens'] is not None and r['http_200'] is not None]
            n=len(sub);response_total=sum(r['http_200'] for r in sub);tokens=sum(r['recorded_total_tokens'] for r in sub)
            proc.append(dict(condition=condition,n=n,tokens=tokens,responses=response_total,
                responses_per_run=ratio(response_total,n),tokens_per_response=ratio(tokens,response_total)))
        n,a=proc
        if n['tokens_per_response'] is not None and a['tokens_per_response'] is not None:
            decomposition.append(dict(stratum=stratum,normal=n,anti=a,
                count_component=(n['responses_per_run']-a['responses_per_run'])*(n['tokens_per_response']+a['tokens_per_response'])/2,
                size_component=(n['tokens_per_response']-a['tokens_per_response'])*(n['responses_per_run']+a['responses_per_run'])/2))
    for batch in BATCHES:
        for pair_id in sorted({r['pair_id'] for r in runs if r['batch']==batch}):
            n,a=[next(r for r in runs if r['batch']==batch and r['pair_id']==pair_id and r['condition']==c) for c in CONDITIONS]
            pair=dict(batch=batch,pair_id=pair_id,pair_key=batch+'/'+str(pair_id),normal_slot=n['slot_key'],anti_slot=a['slot_key'],
                primary_model_pair=all(r['model_id']==PRIMARY_MODEL for r in (n,a)),first_condition=n['first_condition'])
            for name,col in [('token_difference','recorded_total_tokens'),('passed_difference','passed_ids'),('pass_rate_difference_pp','recorded_pass_rate')]:
                pair[name]=a[col]-n[col] if a[col] is not None and n[col] is not None else None
            pairs.append(pair)
    for stratum in (*BATCHES,'cumulative'):
        pp=[p for p in pairs if p['primary_model_pair'] and (stratum=='cumulative' or p['batch']==stratum)]
        for key in ('token_difference','pass_rate_difference_pp'):
            complete=[p for p in pp if p[key] is not None]
            rng=np.random.default_rng(policy['bootstrap']['seed']);draws=np.zeros(policy['bootstrap']['replicates']);size=0
            for batch in BATCHES:
                vals=np.array([p[key] for p in complete if p['batch']==batch])
                if not len(vals):continue
                draws+=vals[rng.integers(0,len(vals),size=(len(draws),len(vals)))].sum(axis=1);size+=len(vals)
            if size:
                lo,hi=np.quantile(draws/size,[.025,.975])
                bootstraps.append(dict(stratum=stratum,metric=key,pairs=size,mean=mean([p[key] for p in complete]),lower=float(lo),upper=float(hi)))
        selections=[('全ペア',pp),('前半', [p for p in pp if p['pair_id']<=(5 if p['batch']=='previous' else 10)]),
                    ('後半',[p for p in pp if p['pair_id']>(5 if p['batch']=='previous' else 10)])]
        selections += [(c+'先行',[p for p in pp if p['first_condition']==c]) for c in CONDITIONS]
        for label,sub in selections:
            sensitivities.append(dict(stratum=stratum,selection=label,pairs=len(sub),
                token_pairs=sum(p['token_difference'] is not None for p in sub),
                score_pairs=sum(p['pass_rate_difference_pp'] is not None for p in sub),
                token_difference=mean([p['token_difference'] for p in sub]),
                pass_rate_difference_pp=mean([p['pass_rate_difference_pp'] for p in sub])))
    loo=[]
    for omit in pairs:
        pp=[p for p in pairs if p!=omit and p['primary_model_pair']]
        loo.append(dict(excluded_pair=omit['pair_key'],token_difference=mean([p['token_difference'] for p in pp]),
            pass_rate_difference_pp=mean([p['pass_rate_difference_pp'] for p in pp])))
    reviewed=[{k:v for k,v in r.items() if k!='raw_source'} for r in runs]
    reachability=[];terminations=[];outliers=[]
    for stratum in (*BATCHES,'cumulative'):
        rr=[r for r in runs if r['model_id']==PRIMARY_MODEL and (stratum=='cumulative' or r['batch']==stratum)]
        for c in CONDITIONS:
            sub=[r for r in rr if r['condition']==c]
            reachability.append(dict(stratum=stratum,condition=c,n=len(sub),
                **{key:describe([r[key] for r in sub]) for key in ('business_assertion_reached','prerequisite_blocked','evaluation_unresolved','reachability_unknown')},
                note='到達と評価未確定は重なる場合があり、足して58にはならない。'))
            for reason in sorted({r['raw_end_reason'] or 'unknown' for r in sub}):
                selected=[r for r in sub if (r['raw_end_reason'] or 'unknown')==reason]
                terminations.append(dict(stratum=stratum,condition=c,reason=reason,n=len(selected),
                    token_mean=mean([r['recorded_total_tokens'] for r in selected]),passed_mean=mean([r['passed_ids'] for r in selected])))
            for key in ('recorded_total_tokens','passed_ids'):
                selected=[r for r in sub if r[key] is not None]
                if not selected:continue
                q1,q3=np.quantile([r[key] for r in selected],[.25,.75]);iqr=q3-q1
                for r in selected:
                    if r[key]<q1-1.5*iqr or r[key]>q3+1.5*iqr:
                        outliers.append(dict(stratum=stratum,condition=c,metric=key,slot_key=r['slot_key'],value=r[key],
                            lower=float(q1-1.5*iqr),upper=float(q3+1.5*iqr),definition='当該バッチ・条件内の1.5 IQR。除外しない。'))
    tables={'runs':reviewed,'summaries':summaries,'pairs':pairs,'ids':ids,'case_results':cases,'feature_runs':features,
        'features':feature_rows,'groups':group_rows,'correlations':correlations,'sensitivity':sensitivities,
        'bootstrap':bootstraps,'leave_one_pair_out':loo,'response_decomposition':decomposition,
        'reachability':reachability,'terminations':terminations,'outliers':outliers}
    for name,rows in tables.items():csv_out(output/(name+'.csv'),rows)
    write(output/'runs.json',reviewed)
    result={'analysis_policy':policy,'tables':tables,'provenance':provenance,'pipeline':pipeline_diagnostics(),
        'review_inputs':{p.name:sha(p) for p in sorted((BASE/'reviews').glob('*.json')) if p.name in ('qualitative-review.json','approval-path.json','evaluation-observations.json')},
        'checks':{'planned':len(runs),'started':len([r for r in runs if r['run_id']]),'ids':len(ids),'cases':len(cases),
            'available_score_runs':sum(r['score_available'] for r in runs),'available_score_ids':sum(i['passed'] is not None for i in ids),
            'unavailable_score_runs_with_raw_outputs':sum(r['source_passed_ids'] is not None and not r['score_available'] for r in runs),
            'unique_run_ids':len({r['run_id'] for r in runs if r['run_id']}),'input_hashes_verified':True},
        'runtime':{'python':platform.python_version(),'numpy':np.__version__}}
    write(output/'results.json',result)
    dbpath=output/'analysis.sqlite';temp=output/'analysis.sqlite.tmp'
    if temp.exists():temp.unlink()
    db=sqlite3.connect(temp)
    db.executescript('''CREATE TABLE runs(slot_key TEXT PRIMARY KEY,run_id TEXT UNIQUE,batch TEXT,condition TEXT,model_id TEXT,recorded_total_tokens INTEGER,passed_ids INTEGER,evaluation_uuid TEXT,evaluation_validity TEXT,row_json TEXT);
CREATE TABLE case_results(run_id TEXT,evaluation_uuid TEXT,test_id TEXT,case_id TEXT,status TEXT,batch TEXT,score_available INTEGER,PRIMARY KEY(run_id,evaluation_uuid,test_id,case_id));
CREATE TABLE id_results(run_id TEXT,test_id TEXT,feature_id TEXT,dependency_group TEXT,passed INTEGER,source_passed INTEGER,PRIMARY KEY(run_id,test_id));
CREATE TABLE provenance(batch TEXT PRIMARY KEY,source_database TEXT,sha256 TEXT,planned_runs INTEGER,raw_cases INTEGER);
CREATE TABLE evaluations(evaluation_uuid TEXT PRIMARY KEY,run_id TEXT,submission_hash TEXT,score_version TEXT,validity TEXT);
CREATE VIEW condition_summary AS SELECT batch,condition,model_id,COUNT(*) planned,COUNT(run_id) started,COUNT(passed_ids) scored,SUM(recorded_total_tokens) recorded_tokens,AVG(recorded_total_tokens) mean_recorded_tokens,AVG(passed_ids) mean_passed_ids FROM runs GROUP BY batch,condition,model_id;
''')
    for r in runs:
        db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(r.get(k) for k in ('slot_key','run_id','batch','condition','model_id','recorded_total_tokens','passed_ids','evaluation_uuid','evaluation_validity'))+(json.dumps(r,ensure_ascii=False,sort_keys=True),))
        if r['evaluation_uuid']:db.execute('INSERT INTO evaluations VALUES(?,?,?,?,?)',(r['evaluation_uuid'],r['run_id'],r['submission_hash'],V6,r['evaluation_validity']))
    db.executemany('INSERT INTO case_results VALUES(?,?,?,?,?,?,?)',[tuple(c[k] for k in ('run_id','evaluation_uuid','test_id','case_id','status','batch','score_available')) for c in cases])
    db.executemany('INSERT INTO id_results VALUES(?,?,?,?,?,?)',[tuple(r[k] for k in ('run_id','test_id','feature_id','dependency_group','passed','source_passed')) for r in ids])
    db.executemany('INSERT INTO provenance VALUES(?,?,?,?,?)',[tuple(r[k] for k in ('batch','source_database','sha256','planned_runs','raw_cases')) for r in provenance])
    db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close();temp.replace(dbpath)
    print(json.dumps(result['checks']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=BASE/'data');a=p.parse_args();build(a.output)

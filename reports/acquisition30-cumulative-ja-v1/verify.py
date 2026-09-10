"""Validate saved inputs, SQLite calculations, manuscript numbers, and source identity."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import re
import sqlite3

BASE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def near(a,b):return a==b or (a is not None and b is not None and math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-8))

def verify(check_originals=False):
    for name,expected in read(BASE/'source-manifest.json')['inputs'].items():assert sha(BASE/name)==expected,name
    d=read(BASE/'data/results.json');tables=d['tables'];runs=tables['runs']
    assert len(runs)==60 and len({r['slot_key'] for r in runs})==60
    assert collections.Counter(r['batch'] for r in runs)=={'previous':20,'additional':40}
    original={}
    for batch in ('previous','additional'):
        with sqlite3.connect((BASE/'source'/batch/'analysis.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            for value, in db.execute('SELECT row_json FROM runs'):
                row=json.loads(value);original[batch+'/'+row['planned_run']]=row
    for row in runs:
        raw=original[row['slot_key']]
        for derived,source in [('recorded_total_tokens','observed_tokens'),('source_total_tokens','total_tokens'),
            ('source_usage_complete','usage_complete'),('source_passed_ids','passed'),('effective_quality','quality_percent'),
            ('submission_hash','submission_hash'),('evaluation_uuid','evaluation_id'),('evaluation_validity','evaluation_validity')]:
            assert row[derived]==raw.get(source),(row['slot_key'],derived)
        available=raw.get('passed') is not None and raw.get('evaluation_outcome') not in ('server_unavailable','evaluator_error','isolation_blocked')
        assert row['score_available']==available
        assert row['passed_ids']==(raw.get('passed') if available else None)
        if row['passed_ids'] is not None:
            assert near(row['recorded_pass_rate'],100*row['passed_ids']/57)
            cases=[c for c in tables['case_results'] if c['run_id']==row['run_id']]
            ids=collections.defaultdict(list)
            for c in cases:ids[c['test_id']].append(c['status'])
            assert len(cases)==58 and len(ids)==57 and len(ids['T-006-05'])==2
            assert sum(all(s=='pass' for s in values) for values in ids.values())==row['passed_ids']
        else:assert row['recorded_pass_rate'] is None
        if row['recorded_input_tokens'] is not None:
            assert row['recorded_input_tokens']+row['recorded_output_tokens']==row['recorded_total_tokens']
        if row['recorded_cached_input_tokens'] is not None:
            assert 0<=row['recorded_cached_input_tokens']<=row['recorded_input_tokens']
    old=[r for r in runs if r['batch']=='previous']
    assert sum(r['recorded_total_tokens'] for r in old)==134321987
    assert {c:sum(r['passed_ids'] for r in old if r['condition']==c) for c in ('normal','anti')}=={'normal':402,'anti':258}
    assert collections.Counter(r['evaluation_validity'] for r in old)=={'invalid':1,'pending':19}
    actual=[r for r in runs if r['run_id']];scored=[r for r in runs if r['passed_ids'] is not None]
    assert len({r['run_id'] for r in actual})==len(actual)
    outputs=[r for r in runs if r['source_passed_ids'] is not None]
    assert len(tables['ids'])==57*len(outputs) and len(tables['case_results'])==58*len(outputs)
    assert sum(i['passed'] is not None for i in tables['ids'])==57*len(scored)
    assert len({(c['run_id'],c['evaluation_uuid'],c['test_id'],c['case_id']) for c in tables['case_results']})==len(tables['case_results'])
    for group,n in [('direct_threshold',3),('downstream_threshold',10),('other',44)]:
        assert len([r for r in tables['ids'] if r['dependency_group']==group])==n*len(outputs)
    sql=read(BASE/'data/sql-evidence.json')
    assert sql['database_sha256']==sha(BASE/'data/analysis.sqlite') and sql['queries_sha256']==sha(BASE/'queries.sql')
    for s in tables['summaries']:
        if s['model']!='muse-spark-1.2-contributor':continue
        q=next((r for r in sql['queries']['C01_condition_statistics']['rows'] if r['stratum']==s['stratum'] and r['condition']==s['condition']),None)
        if q is None:assert s['planned']==0;continue
        for key1,key2 in [('planned','planned'),('started','started'),('scored','scored'),('mean_pass_rate','mean_pass_rate')]:assert near(s[key1],q[key2])
        assert near(s['tokens']['sum'],q['recorded_tokens']) and near(s['tokens']['mean'],q['mean_recorded_tokens'])
        assert near(s['passed_ids']['mean'],q['mean_passed_ids'])
        for metric in ('tokens','passed_ids'):
            median=next((r for r in sql['queries']['C13_medians']['rows'] if r['stratum']==s['stratum'] and r['condition']==s['condition'] and r['metric']==metric),None)
            assert near(s[metric]['median'],median['median_value'] if median else None)
    for p in tables['pairs']:
        if not p['primary_model_pair']:continue
        q=next(r for r in sql['queries']['C08_pairs']['rows'] if r['batch']==p['batch'] and r['pair_id']==p['pair_id'])
        for key in ('token_difference','passed_difference','pass_rate_difference_pp'):assert near(p[key],q[key])
    reviewed=read(BASE/'reviews/qualitative-review.json')['runs']
    candidates={r['run_id']:r for r in read(BASE/'source/additional/qualitative-candidates.json')['runs']}
    assert {q['run_id'] for q in reviewed}==set(candidates),'Complete the visible-source review for every fixed submission'
    for q in reviewed:
        source=candidates[q['run_id']];assert q['submission_hash']==source['submission_hash']
        for citation in q['citations']:assert citation in source['candidates']
    for name,expected in d['review_inputs'].items():assert sha(BASE/'reviews'/name)==expected
    observations=read(BASE/'reviews/evaluation-observations.json')['observations']
    by_uuid={r['run_id']:r for r in actual}
    for o in observations:
        r=by_uuid[o['run_id']]
        assert o['planned_run']==r['planned_run'] and o['batch']==r['batch']
        assert o['submission_hash']==r['submission_hash'] and o['evaluation_uuid']==r['evaluation_uuid']
        assert o['raw_passed_ids']==r['source_passed_ids']
        assert o['new_app_executions']==0 and o['new_evaluations']==0
    claims=read(BASE/'claim-evidence.json')
    report=(BASE/'report.md').read_text(encoding='utf-8-sig');supplement=(BASE/'supplement.md').read_text(encoding='utf-8-sig')
    assert not re.search(r'\{\{[A-Z_]+\}\}',report),'Finish the manuscript placeholders'
    assert '**作成中：' not in report,'The manuscript is still marked as a draft'
    for claim in claims['claims']:
        if claim.get('query'):assert claim['query'] in sql['queries']
        for name in claim.get('evidence_files',[]):assert (BASE/name).is_file(),(claim['id'],name)
        for text in claim.get('required_text',[]):assert text in report+supplement,(claim['id'],text)
    images=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',report)
    assert len(images)==6 and all((BASE/name).is_file() for name in images)
    for name in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',report+supplement):
        if re.match(r'^https?://',name) or name.startswith('#'):continue
        assert (BASE/name.split('#')[0]).exists(),name
    trace=read(BASE/'figures/figure-trace.json')
    assert len(trace['figures'])==6
    for f in trace['figures']:
        assert f['results_sha256']==sha(BASE/'data/results.json') and f['generator_sha256']==sha(BASE/'render_figures.py')
    old_verified=None
    if check_originals:
        root=BASE.parents[1];legacy=read(BASE/'source/additional/legacy-hashes-before.json')
        for name,expected in legacy.items():assert sha(root/name)==expected,'Old original changed: '+name
        for q in reviewed:
            run=root/'results/acquisition20-20260911/batch/runs'/q['planned_run']/'attempt'
            assert sha(run/'snapshot.json')==q['submission_hash']
            for c in q['citations']:
                file=run/'frozen'/c['path'];assert sha(file)==c['sha256']
                assert file.read_text(encoding='utf-8-sig').splitlines()[c['line']-1].strip()==c['text']
        for c in read(BASE/'source/token-components.json')['rows']:
            assert sha(root/c['raw_events'])==c['raw_events_sha256']
        for o in observations:
            run=root/'results/acquisition20-20260911/batch/runs'/o['planned_run']/'attempt'
            ref=read(run/'evaluation-ref.json');private=Path(ref['evaluation_directory'])
            assert o['v6_hash']==ref['score_version']
            assert sha(private/'summary.json')==o['summary_sha256']
            assert sha(private/'results.jsonl')==o['results_sha256']
            for c in o['citations']:
                kind=c['kind']
                if kind=='fixed_source':file=run/'frozen'/c['path']
                elif kind in ('saved_implementation_tool_call','saved_management_source'):file=run/c['path']
                elif kind=='private_saved_evaluation':file=private/c['path']
                elif kind=='private_fixed_evaluator':file=private/c['path']
                else:raise AssertionError('Unknown evidence kind: '+kind)
                assert sha(file)==c['sha256'],c['path']
                if c.get('lines'):
                    body=file.read_text(encoding='utf-8-sig').splitlines()
                    for line in c['lines']:
                        for number,value in line.items():assert body[int(number)-1]==value
                if kind=='saved_implementation_tool_call':
                    e=json.loads(file.read_text().splitlines()[c['line']-1])
                    assert e['type']=='tool.execution_start' and e['data']['toolCallId']==c['tool_call_id']
                    assert hashlib.sha256(e['data']['arguments']['command'].encode()).hexdigest()==c['command_sha256']
        old_verified=len(legacy)
    result={'source_hashes_verified':True,'prior_20_numbers_and_adjudications_unchanged':True,
        'planned':len(runs),'started':len(actual),'scored':len(scored),'run_ids':len(tables['ids']),'cases':len(tables['case_results']),
        'sqlite_queries_cross_checked':True,'qualitative_source_bindings_verified':len(reviewed),
        'saved_evaluation_observations_bound':len(observations),
        'manuscript_claim_markers_verified':len(claims['claims']),'figures':6,'legacy_original_files_verified':old_verified,
        'model_calls':0,'evaluations':0,'report_sha256':sha(BASE/'report.md')}
    (BASE/'checks').mkdir(exist_ok=True)
    (BASE/'checks/verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check-originals',action='store_true');a=p.parse_args();verify(a.check_originals)

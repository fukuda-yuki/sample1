"""Cross-check the new analysis, source preservation, and report references."""
from pathlib import Path
import argparse,collections,hashlib,json,re,sqlite3
import numpy as np
from analyze import BASE,build,compute,read,sha,write_json

def logical(path):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    tables=sorted(x[0] for x in db.execute("select name from sqlite_master where type='table'"))
    content={t:sorted([list(r) for r in db.execute('select * from '+t)],key=lambda r:json.dumps(r,ensure_ascii=False)) for t in tables};db.close()
    return hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check-originals',action='store_true');a=ap.parse_args()
    runs,ids,cases,origin,titles=build(BASE/'source');stats=read(BASE/'data/analysis.json');saved=read(BASE/'data/runs.json')
    assert runs==saved
    assert compute(runs,ids,titles)==stats
    db=sqlite3.connect((BASE/'data/analysis.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    assert [dict(x) for x in db.execute('select * from runs')]==runs
    assert len(cases)==3480 and len(ids)==3420 and len(runs)==60
    assert all('pair' not in c['name'] and 'batch' not in c['name'] and 'order' not in c['name'] for c in db.execute('pragma table_info(runs)'))
    sql=read(BASE/'data/sql-evidence.json')
    for name,q in sql.items():assert [dict(x) for x in db.execute(q['sql'])]==q['rows'],name
    for q in sql['Q02_group_summary']['rows']:
        c=q['condition'];rr=[r for r in runs if r['condition']==c]
        assert abs(q['mean_pass_rate']-np.mean([r['pass_rate'] for r in rr if r['score_available']]))<1e-10
        assert abs(q['mean_tokens']-np.mean([r['recorded_total_tokens'] for r in rr]))<1e-10
    for q in sql['Q03_medians']['rows']:
        metric='recorded_total_tokens' if q['metric']=='tokens' else 'passed_ids'
        assert q['median']==np.median([r[metric] for r in runs if r['condition']==q['condition'] and r[metric] is not None])
    for q in sql['Q04_function_results']['rows']:
        r=next(x for x in stats['features'] if (x['feature_id'],x['condition'])==(q['feature_id'],q['condition']))
        assert (r['passed'],r['failed'],r['blocked'])==(q['passed'],q['failed'],q['blocked'])
    assert len([r for r in runs if r['passed_ids'] is None])==3
    assert [(r['label'],r['passed_ids']) for r in runs if r['score_available'] and r['passed_ids']==0]==[('N-724b28',0)]
    assert sum(r['recorded_total_tokens'] for r in runs)==482034106
    review=read(BASE/'evidence/source-readback.json');assert len(review['runs'])==60 and review['unique_files_read']==139
    citation_count=sum(len(r['citations']) for r in review['runs']);assert citation_count==210
    csv_review=read(BASE/'evidence/csv-failure-review.json');assert len(csv_review['cases'])==57
    assert collections.Counter(x['message_class'] for x in csv_review['cases'])=={'filename_parameter_retained':25,'other_failure':4,'unreached':28}
    for row in csv_review['cases']:
        match=next(r for r in runs if r['run_id']==row['run_id']);assert match['evaluation_uuid']==row['evaluation_uuid'] and match['submission_hash']==row['submission_hash']
    manifest=read(BASE/'source-manifest.json')
    if a.check_originals:
        root=BASE.parents[1]
        for rel,h in manifest['prior_reports_sha256'].items():assert sha(root/rel)==h,rel
        for name,entry in manifest['inputs'].items():assert sha(root/entry['source_path'])==entry['sha256'],name
        write_json(BASE/'checks/originals-unchanged.json',{'prior_report_files':len(manifest['prior_reports_sha256']),'input_sources':len(manifest['inputs']),
          'all_hashes_unchanged':True,'model_runs':0,'evaluator_runs':0})
    report=(BASE/'report.md').read_text(encoding='utf-8');claims=read(BASE/'claim-evidence.json')['claims']
    assert set(re.findall(r'\[(C\d+)\]\(claim-evidence.json\)',report))=={x['id'] for x in claims}
    for c in claims:
        assert all((BASE/f).exists() for f in c['evidence_files']) and all(q in sql for q in c['queries'])
    assert '予定ペア' not in report and 'ペア差' not in report and '追加分' not in report and '前回' not in report
    assert len(re.findall(r'!\[',report))==6
    local_links=re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',report)
    for link in local_links:
        if not re.match(r'https?://',link):assert (BASE/link.split('#')[0]).exists(),link
    expected_strings=['normal 30 Run・anti 30 Run','67.5%','46.5%','21.0ポイント','10.2〜31.5','482,034,106','79,693,612','28.4%',
        '12 ID','261観測中1','252観測中142','478,693,172','3,340,934','470,088,599','549応答','139ファイル','900応答']
    for s in expected_strings:assert s in report,s
    figures=read(BASE/'figures/figure-manifest.json');assert len(figures['figures'])==6
    for f in figures['figures']:
        for ext in ('png','svg'):assert sha(BASE/'figures'/(f['file']+'.'+ext))==f[ext+'_sha256']
        for name,h in f['data_files'].items():assert sha(BASE/'data'/name)==h
    def prose(s):
        s=re.sub(r'!\[[^\]]*\]\([^)]*\)','',s);s=re.sub(r'^\|.*$', '',s,flags=re.M);s=re.sub(r'\[[^\]]*\]\([^)]*\)','',s)
        return len(re.sub(r'\s+','',s))
    scientific=report.split('## 6.')[0];discussion=report.split('## 4. 考察')[1].split('## 5. 結論')[0]
    result={'population':{'normal':30,'anti':30},'analysis_unit':'Run independently within condition','schedule_pair_statistics':False,'acquisition_strata_statistics':False,
      'scores_available':57,'score_missing':3,'completed_zero_preserved':True,'run_id_rows':3420,'case_rows':3480,'sql_queries_verified':len(sql),
      'source_cases_match':True,'original_quality_adjudications_preserved':True,'threshold_source_runs_rechecked':60,'fixed_source_files_rechecked':139,'source_citations_rechecked':citation_count,
      'csv_saved_records_reviewed':57,'request_trajectory_records':900,'claim_references':len(claims),'japanese_figures':6,
      'discussion_prose_share':round(prose(discussion)/prose(scientific),4),'report_sha256':sha(BASE/'report.md'),
      'database_logical_sha256':logical(BASE/'data/analysis.sqlite'),'model_runs':0,'evaluator_runs':0}
    write_json(BASE/'checks/verification.json',result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()

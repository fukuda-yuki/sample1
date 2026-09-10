"""Offline numerical reanalysis. Reads only this folder's copied inputs.

No experiment/measurement/evaluation modules, subprocesses, networking or credentials.
Usage: python -B rebuild.py --output /path/to/new/output
"""
from pathlib import Path
import argparse, csv, hashlib, json, platform, re, shutil, sqlite3, statistics
import numpy as np

BASE=Path(__file__).resolve().parent
DIRECT={"T-006-01","T-006-03","T-006-05"}
DOWNSTREAM={"T-010-01","T-011-01","T-011-02","T-012-01","T-012-02",
            "T-013-01","T-013-02","T-014-01","T-014-02","T-015-01"}
LABELS={"normal":"通常条件","anti":"不整合条件"}

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
def export_csv(path,rows):
    if not rows: return
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for r in rows:
            w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
def query_map():
    chunks=re.split(r"^-- query: ([a-z_]+)\s*$",(BASE/"queries.sql").read_text(),flags=re.M)
    return {chunks[i]:chunks[i+1].strip() for i in range(1,len(chunks),2)}
def describe(xs):
    a=np.array(xs,dtype=float)
    return dict(n=len(xs),sum=float(sum(xs)),mean=float(np.mean(a)),median=float(np.median(a)),
                sd=float(np.std(a,ddof=1)) if len(xs)>1 else None,
                q1=float(np.quantile(a,.25)),q3=float(np.quantile(a,.75)),
                minimum=float(min(a)),maximum=float(max(a)))
def rank(xs):
    order=sorted(range(len(xs)),key=lambda i:xs[i]);out=[0.0]*len(xs);i=0
    while i<len(order):
        j=i+1
        while j<len(order) and xs[order[j]]==xs[order[i]]: j+=1
        for k in order[i:j]:out[k]=(i+j-1)/2+1
        i=j
    return out

def build(output):
    output=output.resolve()
    if output==BASE/"source" or (BASE/"source") in output.parents:
        raise ValueError("Never write over source inputs")
    output.mkdir(parents=True,exist_ok=True)
    manifest=read(BASE/"source-manifest.json")
    for entry in manifest["inputs"]:
        assert digest(BASE/entry["copy"])==entry["sha256"],entry["copy"]
    policy=read(BASE/"analysis-policy.json")
    source=BASE/"source"
    # Original five tables survive unchanged in the new DB. New tables use report_ names.
    shutil.copyfile(source/"analysis.sqlite",output/"analysis.sqlite")
    db=sqlite3.connect(output/"analysis.sqlite");db.row_factory=sqlite3.Row
    raw=[json.loads(r[0]) for r in db.execute("SELECT row_json FROM runs")]
    retention={r["run_id"]:r for r in read(source/"retention.json")["runs"]}
    plan=read(source/"planned-runs.json")["order"]
    by_slot={r["planned_run"]:r for r in plan}
    first={i:min((r for r in plan if r["block"]==i),key=lambda r:r["execution_order"])["condition"] for i in range(1,11)}
    titles=dict(re.findall(r"^## (F-\d{3}): (.+)$",(source/"normal-spec.md").read_text(),flags=re.M))
    db.executescript("""
    CREATE TABLE report_runs(
      planned_run TEXT UNIQUE,run_id TEXT PRIMARY KEY,condition TEXT,condition_label TEXT,
      pair_id INTEGER,execution_order INTEGER,first_condition TEXT,total_tokens INTEGER,
      source_total_tokens INTEGER,source_usage_complete INTEGER,passed INTEGER,failed INTEGER,
      blocked INTEGER,errors INTEGER,denominator INTEGER,raw_score REAL,
      evaluation_id TEXT,submission_hash TEXT,evaluation_validity TEXT,
      elapsed_seconds REAL,http_200 INTEGER,http_400 INTEGER,exit_code INTEGER,
      end_reason TEXT,started_at TEXT,ended_at TEXT,coverage_json TEXT);
    CREATE TABLE report_dimensions(test_id TEXT PRIMARY KEY,feature_id TEXT,feature_title TEXT,
      title TEXT,category TEXT,dependency_group TEXT);
    CREATE TABLE report_feature_coverage(run_id TEXT,feature_id TEXT,cases INTEGER,
      reached INTEGER,prerequisite_blocked INTEGER,evaluation_unresolved INTEGER,
      raw_pass_cases INTEGER,PRIMARY KEY(run_id,feature_id));
    CREATE TABLE report_classifications(run_id TEXT,axis TEXT,label TEXT,cases INTEGER,
      PRIMARY KEY(run_id,axis,label));
    CREATE TABLE report_metadata(name TEXT PRIMARY KEY,value_json TEXT);
    CREATE TABLE report_interpretations(run_id TEXT PRIMARY KEY,planned_run TEXT,condition TEXT,
      recorded_threshold_yen INTEGER,static_threshold_yen INTEGER,explicit_conflict INTEGER,
      evidence_json TEXT);
    CREATE TABLE report_trace_evidence(run_id TEXT,test_id TEXT,evidence_json TEXT,
      PRIMARY KEY(run_id,test_id));
    """)
    for r in raw:
        p=by_slot[r["planned_run"]];t=retention[r["run_id"]]
        assert r["observed_tokens"] is not None
        values=(r["planned_run"],r["run_id"],r["condition"],LABELS[r["condition"]],p["block"],
          p["execution_order"],first[p["block"]],r["observed_tokens"],r["total_tokens"],int(r["usage_complete"]),
          r["passed"],r["failed"],r["blocked"],r["errors"],r["denominator"],100*r["passed"]/r["denominator"],
          r["evaluation_id"],r["submission_hash"],r["evaluation_validity"],t["elapsed_seconds"],
          t["gateway_http"].get("200",0),t["gateway_http"].get("400",0),t["exit_code"],
          r["end_reason"],t["started_at"],t["ended_at"],r["coverage_json"])
        db.execute("INSERT INTO report_runs VALUES("+",".join("?" for _ in values)+")",values)
        cov=json.loads(r["coverage_json"])
        for fid,f in cov["features"].items():
            db.execute("INSERT INTO report_feature_coverage VALUES(?,?,?,?,?,?,?)",
              (r["run_id"],fid,f["cases"],f["business_assertion_reached"],f["prerequisite_blocked"],
               f["evaluation_unresolved"],f["raw_pass_cases"]))
        for axis,key in (("responsibility","responsibilities"),("cause","causes")):
            for label,count in cov[key].items():
                db.execute("INSERT INTO report_classifications VALUES(?,?,?,?)",(r["run_id"],axis,label,count))
    dependency_path=BASE/"evidence/dependency-map.json"
    dependencies={i["evaluation_id"]:i for i in read(dependency_path)["items"]} if dependency_path.exists() else {}
    for item in read(source/"requirements-ledger.json")["items"]:
        test_id=item["evaluation_id"];fid="F-"+test_id[2:5]
        group="direct_threshold" if test_id in DIRECT else "downstream_threshold" if test_id in DOWNSTREAM else "other"
        if dependencies:
            assert dependencies[test_id]["dependency_group"]==group
        db.execute("INSERT INTO report_dimensions VALUES(?,?,?,?,?,?)",
                   (test_id,fid,titles[fid],item["title"],item["category"],group))
    db.executescript("""
    CREATE TABLE report_id_results AS
    SELECT c.run_id,c.evaluation_id test_id,d.feature_id,d.category,d.dependency_group,
      MIN(c.status='pass') passed,COUNT(*) required_cases
    FROM case_results c JOIN report_dimensions d ON c.evaluation_id=d.test_id
    GROUP BY c.run_id,c.evaluation_id;
    CREATE UNIQUE INDEX report_id_pk ON report_id_results(run_id,test_id);
    """)
    for name,value in (("analysis_policy",policy),("source_manifest",manifest)):
        db.execute("INSERT INTO report_metadata VALUES(?,?)",(name,json.dumps(value,ensure_ascii=False)))
    evidence_dir=BASE/"evidence"
    for name in ("qualitative.json","dependency-map.json","private-evidence-index.json"):
        p=evidence_dir/name
        if p.exists():db.execute("INSERT INTO report_metadata VALUES(?,?)",("evidence/"+name,json.dumps(read(p),ensure_ascii=False)))
    if (evidence_dir/"qualitative.json").exists():
        for q in read(evidence_dir/"qualitative.json")["runs"]:
            original_row=next(x for x in raw if x["run_id"]==q["run_id"])
            assert original_row["submission_hash"]==q["submission_hash"]
            assert original_row["evaluation_id"]==q["evaluation_uuid"]
            assert q["recorded_intent"]["threshold_yen"]==q["static_implementation"]["threshold_yen"]
            db.execute("INSERT INTO report_interpretations VALUES(?,?,?,?,?,?,?)",
              (q["run_id"],q["planned_run"],q["condition"],q["recorded_intent"]["threshold_yen"],
               q["static_implementation"]["threshold_yen"],int(q["recorded_intent"]["explicit_ap001_conflict_recorded"]),
               json.dumps(q,ensure_ascii=False)))
    if (evidence_dir/"private-evidence-index.json").exists():
        for e in read(evidence_dir/"private-evidence-index.json")["cases"]:
            db.execute("INSERT INTO report_trace_evidence VALUES(?,?,?)",
                       (e["run_id"],e["evaluation_id"],json.dumps(e,ensure_ascii=False)))
    db.commit()
    queries=query_map()
    tables={name:[dict(r) for r in db.execute(sql)] for name,sql in queries.items()}
    runs=tables["runs"];pairs=tables["pairs"]
    counts={name:db.execute("SELECT COUNT(*) FROM "+name).fetchone()[0] for name in
            ("runs","case_results","evaluations","report_runs","report_id_results","report_dimensions")}
    assert counts=={"runs":20,"case_results":1160,"evaluations":20,"report_runs":20,"report_id_results":1140,"report_dimensions":57},counts
    assert sum(r["total_tokens"] for r in runs)==134321987
    for r in runs:
        n,s=db.execute("SELECT COUNT(*),SUM(passed) FROM report_id_results WHERE run_id=?",(r["run_id"],)).fetchone()
        assert (n,s)==(57,r["passed"])
        assert r["passed"]+r["failed"]+r["blocked"]+r["errors"]==57
        assert db.execute("SELECT COUNT(*) FROM case_results WHERE run_id=?",(r["run_id"],)).fetchone()[0]==58
    original=sqlite3.connect((source/"analysis.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    raw_tables=("runs","case_results","telemetry_refs","evaluations","provenance")
    for table in raw_tables:
        assert sorted(map(tuple,db.execute("SELECT * FROM "+table)))==sorted(original.execute("SELECT * FROM "+table))
    original.close()
    condition_summary=[]
    for condition in ("normal","anti"):
        rr=[r for r in runs if r["condition"]==condition]
        t=describe([r["total_tokens"] for r in rr]);s=describe([r["passed"] for r in rr])
        c=dict(condition=condition,condition_label=LABELS[condition],n=len(rr))
        c.update({"tokens_"+k:v for k,v in t.items()})
        c.update({"passed_"+k:v for k,v in s.items()})
        c.update(score_mean=s["mean"]*100/57,score_median=s["median"]*100/57,
                 tokens_per_pass=t["sum"]/s["sum"],
                 mean_run_tokens_per_pass=statistics.mean(r["total_tokens"]/r["passed"] for r in rr),
                 elapsed_median=statistics.median(r["elapsed_seconds"] for r in rr))
        condition_summary.append(c)
    n,a=condition_summary
    pair_t=np.array([p["token_difference"] for p in pairs])
    pair_s=np.array([p["score_difference_pp"] for p in pairs])
    indices=np.random.default_rng(20260910).integers(0,10,size=(20000,10))
    bootstrap={}
    for name,values in (("tokens",pair_t),("raw_score_pp",pair_s)):
        low,high=np.quantile(values[indices].mean(axis=1),[.025,.975])
        bootstrap[name]={"mean_difference":float(values.mean()),"median_difference":float(np.median(values)),
                         "ci_low":float(low),"ci_high":float(high),"replicates":20000,"seed":20260910}
    sensitivity=[]
    def add_sensitivity(label,pp):
        sensitivity.append(dict(label=label,n_pairs=len(pp),
          token_difference=statistics.mean(p["token_difference"] for p in pp),
          passed_difference=statistics.mean(p["passed_difference"] for p in pp),
          score_difference_pp=statistics.mean(p["score_difference_pp"] for p in pp)))
    add_sensitivity("全10ペア",pairs)
    add_sensitivity("前半5ペア",[p for p in pairs if p["pair_id"]<=5])
    add_sensitivity("後半5ペア",[p for p in pairs if p["pair_id"]>5])
    add_sensitivity("不整合条件が先行",[p for p in pairs if p["first_condition"]=="anti"])
    add_sensitivity("通常条件が先行",[p for p in pairs if p["first_condition"]=="normal"])
    add_sensitivity("最初のペアを除外",[p for p in pairs if p["pair_id"]!=1])
    leave_one_out=[]
    for p in pairs:
        remain=[q for q in pairs if q["pair_id"]!=p["pair_id"]]
        leave_one_out.append(dict(excluded_pair=p["pair_id"],
          token_difference=statistics.mean(q["token_difference"] for q in remain),
          passed_difference=statistics.mean(q["passed_difference"] for q in remain),
          score_difference_pp=statistics.mean(q["score_difference_pp"] for q in remain)))
    correlation=[]
    for condition in ("all","normal","anti"):
        rr=[r for r in runs if condition=="all" or r["condition"]==condition]
        xs=[r["total_tokens"] for r in rr];ys=[r["passed"] for r in rr]
        correlation.append(dict(condition=condition,n=len(rr),pearson=statistics.correlation(xs,ys),
                                spearman=statistics.correlation(rank(xs),rank(ys))))
    old_groups={}
    for condition in ("normal","anti"):
        rr=[r for r in runs if r["condition"]==condition and r["source_usage_complete"]]
        old_groups[condition]=dict(n=len(rr),mean_tokens=statistics.mean(r["source_total_tokens"] for r in rr))
    proc={r["condition"]:r for r in tables["process"]}
    cn,ca=proc["normal"]["http_200"],proc["anti"]["http_200"]
    un,ua=proc["normal"]["tokens_per_200"],proc["anti"]["tokens_per_200"]
    decomposition=dict(call_count_component=(cn-ca)*(un+ua)/2,
      tokens_per_response_component=(un-ua)*(cn+ca)/2,
      total_gap=n["tokens_sum"]-a["tokens_sum"],
      method="Symmetric arithmetic decomposition, not causal attribution",
      response_count_change=ca/cn-1,tokens_per_response_change=ua/un-1)
    assert abs(decomposition["call_count_component"]+decomposition["tokens_per_response_component"]-decomposition["total_gap"])<.0001
    groups={g:{r["condition"]:r for r in tables["groups"] if r["dependency_group"]==g}
            for g in ("direct_threshold","downstream_threshold","other")}
    group_gaps=[dict(dependency_group=g,normal_passed=v["normal"]["passed_ids"],
                    anti_passed=v["anti"]["passed_ids"],gap=v["normal"]["passed_ids"]-v["anti"]["passed_ids"],
                    ids=v["normal"]["requested_ids"]//10) for g,v in groups.items()]
    metrics=dict(token_relative_difference=a["tokens_mean"]/n["tokens_mean"]-1,
      passed_relative_difference=a["passed_mean"]/n["passed_mean"]-1,
      tokens_per_pass_relative_difference=a["tokens_per_pass"]/n["tokens_per_pass"]-1,
      score_variance_ratio=(a["passed_sd"]/n["passed_sd"])**2,
      total_confirmed_tokens=int(n["tokens_sum"]+a["tokens_sum"]),
      affected_gap_share=sum(g["gap"] for g in group_gaps if g["dependency_group"]!="other")/sum(g["gap"] for g in group_gaps),
      token_lower_pairs=sum(p["token_difference"]<0 for p in pairs),
      passed_lower_pairs=sum(p["passed_difference"]<0 for p in pairs),
      passed_equal_pairs=sum(p["passed_difference"]==0 for p in pairs),
      passed_higher_pairs=sum(p["passed_difference"]>0 for p in pairs))
    # Structured evidence is also retained inside SQLite; source originals are untouched.
    db.execute("CREATE TABLE report_query_results(query_id TEXT,row_number INTEGER,row_json TEXT,PRIMARY KEY(query_id,row_number))")
    for q,rr in tables.items():
        for i,r in enumerate(rr):db.execute("INSERT INTO report_query_results VALUES(?,?,?)",(q,i,json.dumps(r,ensure_ascii=False)))
    result=dict(analysis_id=manifest["analysis_id"],source_sqlite_sha256=digest(source/"analysis.sqlite"),
      tables=tables,condition_summary=condition_summary,bootstrap=bootstrap,sensitivity=sensitivity,
      leave_one_pair_out=leave_one_out,correlations=correlation,old_complete_case_summary=old_groups,
      process_decomposition=decomposition,group_gaps=group_gaps,metrics=metrics)
    for k in ("condition_summary","bootstrap","sensitivity","leave_one_pair_out","correlations","old_complete_case_summary","process_decomposition","group_gaps","metrics"):
        db.execute("INSERT INTO report_metadata VALUES(?,?)",("computed/"+k,json.dumps(result[k],ensure_ascii=False)))
    db.commit(); assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok";db.close()
    write(output/"analysis-results.json",result)
    tabledir=output/"tables";tabledir.mkdir(exist_ok=True)
    for name,rr in tables.items():
        # Keep verbose original coverage JSON in SQLite, not the compact Run CSV.
        rr=[{k:v for k,v in r.items() if k!="coverage_json"} for r in rr]
        export_csv(tabledir/(name+".csv"),rr)
    for name,rr in (("condition-summary",condition_summary),("sensitivity",sensitivity),
                   ("leave-one-pair-out",leave_one_out),("correlations",correlation),("group-gaps",group_gaps)):
        export_csv(tabledir/(name+".csv"),rr)
    write(output/"calculation-verification.json",dict(counts=counts,original_tables_identical=True,
      total_tokens=134321987,all_run_scores_reconstructed=True,sqlite_integrity="ok",
      query_ids=list(queries),bootstrap_seed=20260910,bootstrap_replicates=20000,
      no_new_observations=True,no_new_evaluations=True))
    write(output/"analysis-runtime.json",dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,
      numpy=np.__version__,platform=platform.platform()))
    print(json.dumps({"output":str(output),"counts":counts,"metrics":metrics}))
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=BASE)
    args=parser.parse_args()
    build(args.output)

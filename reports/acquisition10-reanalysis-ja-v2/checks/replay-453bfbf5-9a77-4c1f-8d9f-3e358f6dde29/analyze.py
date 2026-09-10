"""Offline reanalysis of frozen inputs. No model, app, evaluator or network calls.

python -B analyze.py --output /path/to/derived-data
The source SQLite is opened read-only and is never rewritten.
"""
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

BASE = Path(__file__).resolve().parent
CONDITIONS = ("normal", "anti")
LABELS = {"normal": "通常条件", "anti": "不整合条件"}
DIRECT = {"T-006-01", "T-006-03", "T-006-05"}
DOWNSTREAM = {"T-010-01", "T-011-01", "T-011-02", "T-012-01", "T-012-02",
              "T-013-01", "T-013-02", "T-014-01", "T-014-02", "T-015-01"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def csv_out(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def describe(values):
    return {"n": len(values), "sum": sum(values), "mean": st.mean(values), "median": st.median(values),
            "sd": st.stdev(values), "min": min(values), "max": max(values)}


def ranks(values):
    return [1 + sum(y < x for y in values) + (sum(y == x for y in values) - 1) / 2 for x in values]


def build(output):
    output = output.resolve()
    source = BASE / "source"
    if output == source or source in output.parents:
        raise ValueError("Output must not overwrite source inputs")
    manifest = read(BASE / "source-manifest.json")
    for entry in manifest["inputs"]:
        assert digest(BASE / entry["file"]) == entry["sha256"], entry["file"]
    db = sqlite3.connect((source / "analysis.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    raw = [json.loads(row[0]) for row in db.execute("SELECT row_json FROM runs")]
    cases = [dict(row) for row in db.execute("SELECT * FROM case_results ORDER BY run_id,evaluation_id,case_id")]
    raw_table_counts = {name: db.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                        for name in ("runs", "case_results", "evaluations", "telemetry_refs", "provenance")}
    db.close()
    expected_cases = {(x["evaluation_id"], x["case_id"]) for x in read(source / "case-manifest.json")["cases"]}
    assert len(expected_cases) == 58
    plan = read(source / "planned-runs.json")["order"]
    planned = {r["planned_run"]: r for r in plan}
    retained = {r["run_id"]: r for r in read(source / "retention.json")["runs"]}
    qualitative = {r["run_id"]: r for r in read(source / "qualitative.json")["runs"]}
    dimensions = {r["evaluation_id"]: r for r in read(source / "requirements-ledger.json")["items"]}
    dependencies = {r["evaluation_id"]: r for r in read(source / "dependency-map.json")["items"]}
    titles = dict(re.findall(r"^## (F-\d{3}): (.+)$", (source / "normal-spec.md").read_text(encoding="utf-8"), re.M))
    assert len(dimensions) == 57 and len(titles) == 20
    assert len(raw) == len(retained) == len(qualitative) == len(planned) == 20
    assert {r["planned_run"] for r in raw} == set(planned)
    runs, ids, features, interpretations, coverage, classifications = [], [], [], [], [], []
    for r in sorted(raw, key=lambda x: planned[x["planned_run"]]["execution_order"]):
        run_id = r["run_id"]
        p, t, q = planned[r["planned_run"]], retained[run_id], qualitative[run_id]
        assert r["submission_hash"] == t["submission_hash"] == q["submission_hash"]
        assert r["evaluation_id"] == q["evaluation_uuid"]
        rc = [c for c in cases if c["run_id"] == run_id]
        assert len(rc) == 58 and {(c["evaluation_id"], c["case_id"]) for c in rc} == expected_cases
        assert all(c["status"] in {"pass", "fail", "blocked", "error"} for c in rc)
        first = min((v for v in plan if v["block"] == p["block"]), key=lambda v: v["execution_order"])["condition"]
        assert isinstance(r["observed_tokens"], int) and r["observed_tokens"] >= 0
        runs.append(dict(planned_run=r["planned_run"], run_id=run_id, condition=r["condition"],
            pair_id=p["block"], execution_order=p["execution_order"], first_condition=first,
            recorded_total_tokens=r["observed_tokens"], source_total_tokens=r["total_tokens"],
            source_usage_complete=r["usage_complete"], passed_ids=r["passed"], denominator=57,
            recorded_pass_rate=100*r["passed"]/57, evaluation_uuid=r["evaluation_id"],
            evaluation_validity=r["evaluation_validity"], submission_hash=r["submission_hash"],
            elapsed_seconds=t["elapsed_seconds"], http_200=t["gateway_http"].get("200", 0),
            http_400=t["gateway_http"].get("400", 0), raw_end_reason=t["raw_end_reason"], exit_code=t["exit_code"]))
        ri = []
        for test_id, dimension in sorted(dimensions.items()):
            cc = [c for c in rc if c["evaluation_id"] == test_id]
            group = "direct_threshold" if test_id in DIRECT else "downstream_threshold" if test_id in DOWNSTREAM else "other"
            assert dependencies[test_id]["dependency_group"] == group
            item = dict(run_id=run_id, planned_run=r["planned_run"], condition=r["condition"],
                test_id=test_id, feature_id="F-"+test_id[2:5], category=dimension["category"],
                dependency_group=group, required_cases=len(cc), passed=int(all(c["status"] == "pass" for c in cc)))
            assert len(cc) == (2 if test_id == "T-006-05" else 1)
            ri.append(item)
        assert sum(i["passed"] for i in ri) == r["passed"] and r["denominator"] == 57
        ids.extend(ri)
        cov = json.loads(r["coverage_json"])
        for fid in sorted(titles):
            fi = [i for i in ri if i["feature_id"] == fid]
            cf = cov["features"][fid]
            features.append(dict(run_id=run_id, planned_run=r["planned_run"], condition=r["condition"],
                feature_id=fid, feature_title=titles[fid], ids=len(fi), passed_ids=sum(i["passed"] for i in fi),
                recorded_pass_rate=100*sum(i["passed"] for i in fi)/len(fi)))
            coverage.append(dict(run_id=run_id, condition=r["condition"], feature_id=fid,
                requested_cases=cf["cases"], business_assertion_reached=cf["business_assertion_reached"],
                prerequisite_blocked=cf["prerequisite_blocked"], evaluation_unresolved=cf["evaluation_unresolved"]))
        for axis, values in (("responsibility", cov["responsibilities"]), ("cause", cov["causes"])):
            for label, count in values.items():
                classifications.append(dict(run_id=run_id, condition=r["condition"], axis=axis, label=label, cases=count))
        fingerprint = {(c["evaluation_id"], c["case_id"]): c["status"] for c in rc}
        pattern = {("T-006-01", "main"): "fail", ("T-006-02", "main"): "pass",
                   ("T-006-03", "main"): "fail", ("T-006-04", "main"): "pass",
                   ("T-006-05", "lower"): "fail", ("T-006-05", "upper"): "pass"}
        for c in q["saved_outcomes"]["threshold_cases"]:
            assert fingerprint[(c["evaluation_id"], c["case_id"])] == c["status"]
        interpretations.append(dict(planned_run=r["planned_run"], run_id=run_id, condition=r["condition"],
            recorded_threshold_yen=q["recorded_intent"]["threshold_yen"],
            static_threshold_yen=q["static_implementation"]["threshold_yen"],
            conflict_recorded=q["recorded_intent"]["explicit_ap001_conflict_recorded"],
            saved_threshold_pattern_matches=all(fingerprint[k] == value for k, value in pattern.items())))
    summary, pairs, group_summary, feature_summary, coverage_summary, case_summary = [], [], [], [], [], []
    for condition in CONDITIONS:
        rr = [r for r in runs if r["condition"] == condition]
        assert len(rr) == 10
        tokens, passed = describe([r["recorded_total_tokens"] for r in rr]), describe([r["passed_ids"] for r in rr])
        summary.append(dict(condition=condition, n=10, recorded_tokens=tokens, passed_ids=passed,
            mean_recorded_pass_rate=100*passed["mean"]/57, median_recorded_pass_rate=100*passed["median"]/57,
            recorded_tokens_per_passed_id=tokens["sum"]/passed["sum"],
            mean_run_recorded_tokens_per_passed_id=st.mean(r["recorded_total_tokens"]/r["passed_ids"] for r in rr),
            source_usage_incomplete=sum(not r["source_usage_complete"] for r in rr),
            evaluation_validity=dict(collections.Counter(r["evaluation_validity"] for r in rr))))
        for group in ("direct_threshold", "downstream_threshold", "other"):
            ii = [i for i in ids if i["condition"] == condition and i["dependency_group"] == group]
            group_summary.append(dict(condition=condition, group=group, ids_per_run=len(ii)//10,
                requested_ids=len(ii), passed_ids=sum(i["passed"] for i in ii),
                recorded_pass_rate=100*sum(i["passed"] for i in ii)/len(ii)))
        for fid in sorted(titles):
            ff = [f for f in features if f["condition"] == condition and f["feature_id"] == fid]
            feature_summary.append(dict(condition=condition, feature_id=fid, feature_title=titles[fid],
                ids_per_run=ff[0]["ids"], passed_ids=sum(f["passed_ids"] for f in ff),
                requested_ids=sum(f["ids"] for f in ff),
                recorded_pass_rate=100*sum(f["passed_ids"] for f in ff)/sum(f["ids"] for f in ff)))
        cc = [c for c in coverage if c["condition"] == condition]
        coverage_summary.append(dict(condition=condition, **{k: sum(c[k] for c in cc) for k in
            ("requested_cases", "business_assertion_reached", "prerequisite_blocked", "evaluation_unresolved")}))
        run_ids = {r["run_id"] for r in rr}
        counts = collections.Counter(c["status"] for c in cases if c["run_id"] in run_ids)
        case_summary.append(dict(condition=condition, **{k: counts[k] for k in ("pass", "fail", "blocked", "error")}))
    for pair_id in range(1, 11):
        n, a = [next(r for r in runs if r["pair_id"] == pair_id and r["condition"] == c) for c in CONDITIONS]
        pairs.append(dict(pair_id=pair_id, first_condition=n["first_condition"], normal_run=n["planned_run"], anti_run=a["planned_run"],
            normal_tokens=n["recorded_total_tokens"], anti_tokens=a["recorded_total_tokens"],
            normal_passed=n["passed_ids"], anti_passed=a["passed_ids"],
            token_difference=a["recorded_total_tokens"]-n["recorded_total_tokens"],
            passed_difference=a["passed_ids"]-n["passed_ids"],
            pass_rate_difference_pp=a["recorded_pass_rate"]-n["recorded_pass_rate"]))
    sensitivities = []
    def sensitivity(label, pp):
        sensitivities.append(dict(label=label, pairs=len(pp),
            token_difference=st.mean(p["token_difference"] for p in pp),
            passed_difference=st.mean(p["passed_difference"] for p in pp),
            pass_rate_difference_pp=st.mean(p["pass_rate_difference_pp"] for p in pp)))
    sensitivity("全10ペア", pairs)
    sensitivity("前半5ペア", pairs[:5]); sensitivity("後半5ペア", pairs[5:])
    for c in ("normal", "anti"):
        sensitivity(LABELS[c]+"が先行", [p for p in pairs if p["first_condition"] == c])
    sensitivity("最初のペアを除外", pairs[1:])
    loo = [dict(excluded_pair=p["pair_id"], token_difference=st.mean(q["token_difference"] for q in pairs if q != p),
           passed_difference=st.mean(q["passed_difference"] for q in pairs if q != p)) for p in pairs]
    bootstrap = {}
    indices = np.random.default_rng(20260910).integers(0, 10, size=(20000, 10))
    for key in ("token_difference", "pass_rate_difference_pp"):
        values = np.array([p[key] for p in pairs])
        lower, upper = np.quantile(values[indices].mean(axis=1), [.025, .975])
        bootstrap[key] = dict(mean=float(values.mean()), lower=float(lower), upper=float(upper))
    correlations = []
    for condition in ("all", *CONDITIONS):
        rr = [r for r in runs if condition == "all" or r["condition"] == condition]
        x, y = [r["recorded_total_tokens"] for r in rr], [r["passed_ids"] for r in rr]
        correlations.append(dict(condition=condition, n=len(rr), pearson=st.correlation(x, y), spearman=st.correlation(ranks(x), ranks(y))))
    pareto = [r for r in runs if not any(o["recorded_total_tokens"] <= r["recorded_total_tokens"] and o["passed_ids"] >= r["passed_ids"]
             and (o["recorded_total_tokens"] < r["recorded_total_tokens"] or o["passed_ids"] > r["passed_ids"]) for o in runs)]
    process = []
    for c in CONDITIONS:
        rr = [r for r in runs if r["condition"] == c]
        total, responses = sum(r["recorded_total_tokens"] for r in rr), sum(r["http_200"] for r in rr)
        process.append(dict(condition=c, recorded_tokens=total, http_200=responses,
            recorded_tokens_per_200=total/responses, mean_elapsed_seconds=st.mean(r["elapsed_seconds"] for r in rr),
            median_elapsed_seconds=st.median(r["elapsed_seconds"] for r in rr)))
    pn, pa = process
    process_decomposition = dict(count_component=(pn["http_200"]-pa["http_200"])*(pn["recorded_tokens_per_200"]+pa["recorded_tokens_per_200"])/2,
        size_component=(pn["recorded_tokens_per_200"]-pa["recorded_tokens_per_200"])*(pn["http_200"]+pa["http_200"])/2)
    n, a = summary
    assert n["recorded_tokens"]["sum"] == 71287304 and a["recorded_tokens"]["sum"] == 63034683
    assert n["passed_ids"]["sum"] == 402 and a["passed_ids"]["sum"] == 258
    assert sum(i["saved_threshold_pattern_matches"] for i in interpretations if i["condition"] == "anti") == 7
    gaps = []
    for group in ("direct_threshold", "downstream_threshold", "other"):
        gn, ga = [next(g for g in group_summary if g["condition"] == c and g["group"] == group) for c in CONDITIONS]
        gaps.append(dict(group=group, ids_per_run=gn["ids_per_run"], normal_passed=gn["passed_ids"],
                         anti_passed=ga["passed_ids"], gap=gn["passed_ids"]-ga["passed_ids"]))
    assert [g["gap"] for g in gaps] == [30, 60, 54]
    metrics = dict(recorded_total_tokens=sum(r["recorded_total_tokens"] for r in runs),
        token_relative_difference=a["recorded_tokens"]["mean"]/n["recorded_tokens"]["mean"]-1,
        passed_relative_difference=a["passed_ids"]["mean"]/n["passed_ids"]["mean"]-1,
        tokens_per_pass_relative_difference=a["recorded_tokens_per_passed_id"]/n["recorded_tokens_per_passed_id"]-1,
        grouped_gap_share=sum(g["gap"] for g in gaps[:2])/sum(g["gap"] for g in gaps),
        fewer_token_pairs=sum(p["token_difference"] < 0 for p in pairs),
        fewer_passed_pairs=sum(p["passed_difference"] < 0 for p in pairs),
        equal_passed_pairs=sum(p["passed_difference"] == 0 for p in pairs),
        more_passed_pairs=sum(p["passed_difference"] > 0 for p in pairs),
        unconfirmed_case_responsibilities=sum(c["cases"] for c in classifications if c["axis"] == "responsibility" and c["label"] == "unconfirmed"))
    assert metrics["unconfirmed_case_responsibilities"] == 477
    output.mkdir(parents=True, exist_ok=True)
    tables = dict(runs=runs, pairs=pairs, ids=ids, feature_runs=features, features=feature_summary,
        groups=group_summary, group_gaps=gaps, interpretations=interpretations, coverage=coverage_summary,
        raw_case_status=case_summary, classifications=classifications, sensitivity=sensitivities,
        leave_one_pair_out=loo, correlations=correlations, pareto=pareto, process=process)
    result = dict(analysis_id=manifest["analysis_id"], source_sqlite_sha256=manifest["source_sqlite_sha256"],
        summary=summary, tables=tables, metrics=metrics, bootstrap=bootstrap, process_decomposition=process_decomposition)
    save(output / "results.json", result)
    for name, rows in tables.items():
        csv_out(output / (name+".csv"), rows)
    save(output / "calculation-verification.json", dict(original_table_counts=raw_table_counts,
        runs=20, run_ids=1140, cases=1160, source_hashes_match=True, all_required_cases_match=True,
        all_id_scores_match=True, all_evaluation_uuids_match=True, all_submission_hashes_match=True,
        original_sqlite_opened_read_only=True, source_validity_counts={"invalid": 1, "pending": 19},
        recorded_total_tokens=metrics["recorded_total_tokens"], new_implementation_runs=0, new_evaluations=0))
    save(output / "runtime.json", dict(python=platform.python_version(), numpy=np.__version__, sqlite=sqlite3.sqlite_version))
    print(json.dumps({"output": str(output), "runs": len(runs), "ids": len(ids), "cases": len(cases), "metrics": metrics}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=BASE / "data")
    build(parser.parse_args().output)

"""Verify source preservation, arithmetic, manuscript tables, and copied-input replay.

This verifies the report, not the study applications or the validity of v6 scores.
All verification work is retained under checks; no recursive deletion is used.
"""
from pathlib import Path
import collections
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import statistics as st
import subprocess
import sys
import uuid

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024*1024), b""):
            h.update(part)
    return h.hexdigest()


def source_refs(value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            yield value["path"], value["sha256"]
        for item in value.values():
            yield from source_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from source_refs(item)


def local_path(name):
    if sys.platform == "win32" and name.startswith("/mnt/c/"):
        return Path("C:/"+name[7:])
    return Path(name)


def markdown_rows(text):
    return [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.startswith("|")]


def main():
    checks = BASE/"checks"
    checks.mkdir(exist_ok=True)
    manifest = read(BASE/"source-manifest.json")
    for entry in manifest["inputs"]:
        assert sha(BASE/entry["file"]) == entry["sha256"], entry["file"]
        assert sha(ROOT/entry["origin"]) == entry["sha256"], entry["origin"]
    for name, expected in manifest["original_report_inventory"].items():
        assert sha(ROOT/name) == expected, name
    for name, expected in manifest["distributed_contracts"].items():
        assert sha(ROOT/name) == expected, name

    # Verify that the retained reading index still points to unchanged original bytes.
    refs = {}
    for name in ("qualitative.json", "dependency-map.json", "private-evidence-index.json"):
        for file, expected in source_refs(read(BASE/"source"/name)):
            if file in refs:
                assert refs[file] == expected, file
            refs[file] = expected
    for file, expected in refs.items():
        assert sha(local_path(file)) == expected, file
    qualitative = read(BASE/"source/qualitative.json")["runs"]
    for q in qualitative:
        citation = q["recorded_intent"]["citation"]
        lines = local_path(citation["path"]).read_text(encoding="utf-8-sig").splitlines()
        excerpt = "\n".join(lines[citation["line_start"]-1:citation["line_end"]])
        assert q["recorded_intent"]["text"].strip() in excerpt.strip(), q["planned_run"]
        for branch in q["static_implementation"]["branches"]:
            c = branch["citation"]
            lines = local_path(c["path"]).read_text(encoding="utf-8-sig").splitlines()
            assert branch["line"].strip() in "\n".join(lines[c["line_start"]-1:c["line_end"]]), q["planned_run"]

    db = sqlite3.connect((BASE/"source/analysis.sqlite").as_uri()+"?mode=ro&immutable=1", uri=True)
    raw = [json.loads(row[0]) for row in db.execute("SELECT row_json FROM runs")]
    cases = list(db.execute("SELECT run_id,evaluation_id,case_id,status FROM case_results"))
    db.close()
    derived = read(BASE/"data/results.json")
    by_id = {r["run_id"]: r for r in raw}
    assert len(raw) == 20 and len(cases) == 1160
    assert len({(r, t) for r, t, _, _ in cases}) == 1140
    assert len({(r, t, c) for r, t, c, _ in cases}) == 1160
    for r in derived["tables"]["runs"]:
        original = by_id[r["run_id"]]
        assert r["recorded_total_tokens"] == original["observed_tokens"]
        assert r["source_total_tokens"] == original["total_tokens"]
        assert r["source_usage_complete"] == original["usage_complete"]
        assert r["evaluation_validity"] == original["evaluation_validity"]
        assert r["submission_hash"] == original["submission_hash"]
        tc = collections.defaultdict(list)
        for rid, tid, cid, status in cases:
            if rid == r["run_id"]:
                tc[tid].append(status)
        assert len(tc) == 57 and len(tc["T-006-05"]) == 2
        assert sum(all(s == "pass" for s in statuses) for statuses in tc.values()) == r["passed_ids"]
    assert sum(r["observed_tokens"] for r in raw) == 134321987
    report = (BASE/"report.md").read_text(encoding="utf-8")
    supplement = (BASE/"supplement.md").read_text(encoding="utf-8")
    rows = markdown_rows(report)
    row = lambda title: next(r for r in rows if r[0] == title)
    for column, condition in [(1, "normal"), (2, "anti")]:
        rr = [r for r in raw if r["condition"] == condition]
        token = [r["observed_tokens"] for r in rr]; passed = [r["passed"] for r in rr]
        assert row("総消費トークン数")[column] == f"{sum(token):,}"
        assert row("1 Runあたりの平均消費トークン")[column] == f"{st.mean(token):,.1f}"
        assert row("消費トークンの中央値")[column] == f"{st.median(token):,.0f}"
        assert row("合格ID数の平均")[column] == f"{st.mean(passed):.1f} / 57"
        assert row("合格率の平均")[column] == f"{st.mean(passed)*100/57:.1f}%"
        assert row("合格ID数の中央値")[column] == f"{st.median(passed):.0f}"
        assert row("合格ID数の標準偏差")[column] == f"{st.stdev(passed):.2f}"
        for output_key, label in [("pass", "合格と記録されたケース数"), ("fail", "failと記録されたケース数"),
                                  ("blocked", "blockedと記録されたケース数"), ("error", "errorと記録されたケース数")]:
            count = sum(status == output_key and by_id[rid]["condition"] == condition for rid, _, _, status in cases)
            assert row(label)[column] == str(count)
        cov = next(c for c in derived["tables"]["coverage"] if c["condition"] == condition)
        assert row("業務上の判定まで到達したケース数")[column] == str(cov["business_assertion_reached"])
        assert row("別途分類された前提未成立のケース数")[column] == str(cov["prerequisite_blocked"])
    for p in derived["tables"]["pairs"]:
        assert row(f"{p['pair_id']:03}")[1:] == [f"{p['normal_tokens']:,}", str(p["normal_passed"]), f"{p['anti_tokens']:,}", str(p["anti_passed"])]
    for group, title in [("direct_threshold", "閾値を直接確認する3 ID"), ("downstream_threshold", "承認者の前提に依存する後続10 ID"), ("other", "その他44 ID")]:
        gg = [next(g for g in derived["tables"]["groups"] if g["group"] == group and g["condition"] == c) for c in ("normal", "anti")]
        assert row(title)[1:3] == [f"{g['passed_ids']} / {g['requested_ids']}" for g in gg]
        assert row(title)[3] == str(gg[0]["passed_ids"]-gg[1]["passed_ids"])
    supplementary_rows = markdown_rows(supplement)
    for c, title in [("all", "全体"), ("normal", "通常条件内"), ("anti", "不整合条件内")]:
        r = next(r for r in supplementary_rows if r[0] == title)
        corr = next(r for r in derived["tables"]["correlations"] if r["condition"] == c)
        assert r[2:] == [f"{corr['pearson']:.3f}".replace("-", "−"), f"{corr['spearman']:.3f}".replace("-", "−")]
    for phrase in ("134,321,987", "11.6%", "25.3ポイント", "37.8%", "62.5%", "477ケース"):
        assert phrase in report, phrase
    assert "確定総トークン" not in report+supplement
    assert len(re.findall(r"^!\[", report, re.M)) == 6
    headings = re.findall(r"^## (\d)\. (.+)$", report, re.M)
    assert [x[0] for x in headings] == ["1", "2", "3", "4", "5"]
    narrative = "\n".join(line for line in report.splitlines() if not line.startswith(("|", "!", "#")))
    discussion = re.search(r"^## 4\..*?\n(.*?)^## 5\.", report, re.M|re.S).group(1)
    assert 8000 <= len(narrative) <= 12000
    for name in ("report.md", "supplement.md", "sources.md", "reproduce.md"):
        text = (BASE/name).read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if link.startswith(("https://", "http://", "#")):
                continue
            file, _, fragment = link.partition("#")
            target = (BASE/file).resolve()
            assert target.is_file(), (name, link)
            if fragment:
                assert f'id="{fragment}"' in target.read_text(encoding="utf-8"), (name, link)

    # Copy only the inputs and generator code, then rerun in a separate process.
    replay = checks/("replay-"+str(uuid.uuid4()))
    replay.mkdir()
    (replay/"source").mkdir()
    for entry in manifest["inputs"]:
        shutil.copyfile(BASE/entry["file"], replay/entry["file"])
    for file in ("source-manifest.json", "analysis-policy.json", "analyze.py", "render_figures.py"):
        shutil.copyfile(BASE/file, replay/file)
    outputs = []
    for script in ("analyze.py", "render_figures.py"):
        result = subprocess.run([sys.executable, "-B", str(replay/script)], cwd=replay,
                                capture_output=True, text=True, encoding="utf-8")
        outputs.append(dict(script=script, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        assert result.returncode == 0, outputs[-1]
    compared = {}
    for folder in ("data", "figures"):
        originals = {p.name for p in (BASE/folder).iterdir() if p.is_file()}
        regenerated = {p.name for p in (replay/folder).iterdir() if p.is_file()}
        assert originals == regenerated, folder
        for name in sorted(originals):
            a, b = BASE/folder/name, replay/folder/name
            assert a.read_bytes() == b.read_bytes(), str(a)
            compared[folder+"/"+name] = sha(a)
    for file, expected in manifest["original_report_inventory"].items():
        assert sha(ROOT/file) == expected, file
    result = dict(report_sha256=sha(BASE/"report.md"), source_sqlite_sha256=manifest["source_sqlite_sha256"],
        source_inputs=len(manifest["inputs"]), original_report_files_unchanged=len(manifest["original_report_inventory"]),
        distributed_contracts_unchanged=len(manifest["distributed_contracts"]), unchanged_referenced_source_files=len(refs),
        twenty_recorded_explanations_and_code_excerpts_match=True, runs=20, run_ids=1140, cases=1160,
        manuscript_tables_verified=True, supplementary_correlations_verified=True,
        narrative_characters=len(narrative), markdown_characters=len(report), discussion_characters=len(discussion),
        linked_local_files_exist=True, replay_directory=str(replay.relative_to(BASE)),
        regenerated_files_byte_identical=compared, subprocesses=outputs,
        scope="Arithmetic, preservation and reproduction checks only; not an OS isolation test or an evaluation-validity adjudication.")
    (checks/"verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("regenerated_files_byte_identical", "subprocesses")}))


if __name__ == "__main__":
    main()

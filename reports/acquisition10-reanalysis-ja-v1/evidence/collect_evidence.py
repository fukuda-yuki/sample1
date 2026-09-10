"""Read saved evidence only; never launch the application, evaluator, or a model.

Usage (WSL): python -B collect_evidence.py --root /mnt/c/Users/mwam0/Documents/ls/sample1
Outputs are restricted to this evidence directory. Existing identical outputs are accepted;
different existing outputs are refused. Private evaluator source/trace bodies are not copied.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Reader:
    def __init__(self):
        self.records = {}

    def record(self, path, before, after, expected=None, basis=None):
        assert before == after, f"Original changed during read: {path}"
        if expected is not None:
            assert before == expected, f"Expected original hash mismatch: {path}"
        key = str(path.resolve())
        entry = self.records.setdefault(key, {
            "path": key, "sha256_before": before, "sha256_after": after,
            "unchanged": True, "read_count": 0, "expected_hash_checks": [],
        })
        assert entry["sha256_before"] == before, f"Original changed between reads: {path}"
        entry["read_count"] += 1
        if expected is not None:
            check = {"expected_sha256": expected, "basis": basis, "matched": True}
            if check not in entry["expected_hash_checks"]:
                entry["expected_hash_checks"].append(check)

    def read(self, path, expected=None, basis=None):
        path = Path(path)
        data = path.read_bytes()
        self.record(path, digest(data), digest(path.read_bytes()), expected, basis)
        return data

    def obj(self, path, expected=None, basis=None):
        return json.loads(self.read(path, expected, basis))

    def citation(self, path, start=None, end=None):
        path = Path(path).resolve()
        out = {"path": str(path), "sha256": self.records[str(path)]["sha256_before"]}
        if start is not None:
            out["line_start"] = start
            out["line_end"] = end if end is not None else start
        return out


THRESHOLD = re.compile(r"(?<!\d)(?:[15][_,]?000[_,]?000|500[_,]?000|499[_,]?999|999[_,]?999)(?!\d)|[15]00?万(?:円)?|閾値")
BRANCH = re.compile(r"(?<!\d)(?:1000000|1_000_000|500000|500_000|499999|499_999|999999|999_999)(?!\d)")
DIRECT = {"T-006-01", "T-006-03", "T-006-05"}
DOWNSTREAM = {
    "T-010-01", "T-011-01", "T-011-02", "T-012-01", "T-012-02",
    "T-013-01", "T-013-02", "T-014-01", "T-014-02", "T-015-01",
}
EXPECTED_ROLE = {
    "T-010-01": "50万円申請を課長が承認する前提",
    "T-011-01": "50万円申請を課長が差し戻す前提",
    "T-011-02": "50万円申請を課長が差し戻せる前提で未入力を検査",
    "T-012-01": "50万円申請の取消メールを課長宛に期待",
    "T-012-02": "50万円申請を課長が承認してから取消禁止を検査",
    "T-013-01": "50万円申請を課長が差し戻し、再提出通知も課長宛に期待",
    "T-013-02": "50万円申請を課長が承認してから不正遷移を検査",
    "T-014-01": "50万円申請の承認依頼メールを課長宛に期待",
    "T-014-02": "50万円申請を課長が承認した後の完了メールを検査",
    "T-015-01": "50万円申請を課長が差し戻し、再提出・承認する履歴を検査",
}


def threshold_section(text):
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if THRESHOLD.search(line) and ("課長" in line or "部長" in line)]
    if not hits:
        return None
    i = hits[0]
    start = i
    while start > 0 and not lines[start].startswith("## "):
        start -= 1
    end = i + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    return {"line_start": start + 1, "line_end": end, "text": "\n".join(lines[start:end]).strip()}


def matching_excerpt(text):
    lines = text.splitlines()
    keep = []
    for i, line in enumerate(lines):
        if THRESHOLD.search(line) or re.search(r"(?:500k|1000k|DECISIONS\.md)", line, re.I):
            if "DECISIONS.md" in line and not THRESHOLD.search(line):
                continue
            keep.append({"content_line": i + 1, "text": line[:1500]})
    return keep


def saved_messages(raw, citation, expected_threshold):
    matches = []
    for lineno, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "assistant.message":
            continue
        data = event.get("data", {})
        content = data.get("content")
        base = {**citation, "line_start": lineno, "line_end": lineno,
                "event_id": event.get("id"), "timestamp": event.get("timestamp"),
                "event_type": "assistant.message", "message_id": data.get("messageId")}
        if isinstance(content, str):
            excerpts = matching_excerpt(content)
            if excerpts:
                matches.append({**base, "kind": "assistant_visible_text", "field": "data.content", "excerpts": excerpts})
        for ti, request in enumerate(data.get("toolRequests") or []):
            args = request.get("arguments", {})
            if not isinstance(args, dict):
                continue
            if str(args.get("path", "")).replace("\\", "/").endswith("/DECISIONS.md"):
                text = args.get("file_text") or args.get("new_str") or ""
                section = threshold_section(text)
                if section:
                    matches.append({**base, "kind": "assistant_document_write_request",
                                    "field": f"data.toolRequests[{ti}].arguments",
                                    "tool_name": request.get("name"), "tool_call_id": request.get("toolCallId"),
                                    "excerpt": section["text"],
                                    "interpretation": "保存済み文書作成要求。独立の発言や内心の証明としては数えない。"})
    numeric_forms = ("500000", "499999", "50万", "500k") if expected_threshold == 500000 else ("1000000", "999999", "100万", "1000k")
    for match in matches:
        text = match.get("excerpt") or "\n".join(x["text"] for x in match.get("excerpts", []))
        normalized = text.replace(",", "").replace("_", "").lower()
        explicit = any(form in normalized for form in numeric_forms)
        match["supports_explicit_recorded_threshold_value"] = explicit
        match["corroboration_scope"] = "採用閾値の数値を含む自己記録" if explicit else "関連作業・矛盾への言及のみ。採用数値の明言として数えない。"
        match["verification_limit"] = "保存されたモデル出力。自己申告されたテストの成功を今回独立検証したものではない。"
    return matches


def local_path(s):
    if s.startswith("/mnt/c/") and Path("C:/").exists():
        return Path("C:/" + s[7:])
    return Path(s)


def write_output(path, obj):
    data = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists():
        assert path.read_bytes() == data, f"Refusing to overwrite different evidence: {path}"
    else:
        with path.open("xb") as f:
            f.write(data)
    return digest(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = Path(__file__).resolve().parent
    assert output == (root / "reports/acquisition10-reanalysis-ja-v1/evidence").resolve()
    rd = Reader()
    db = root / "reports/acquisition10-preserve-first-20260910/analysis.sqlite"
    db_before = digest(rd.read(db))
    con = sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)
    con.execute("PRAGMA query_only=ON")
    rows = [json.loads(x[0]) for x in con.execute("SELECT row_json FROM runs ORDER BY planned_run")]
    provenance = json.loads(con.execute("SELECT document_json FROM provenance").fetchone()[0])
    sql_cases = [tuple(x) for x in con.execute("SELECT run_id,evaluation_id,case_id,status FROM case_results ORDER BY 1,2,3")]
    con.close()
    rd.record(db, db_before, digest(db.read_bytes()), basis="immutable/read-only SQLite connection")
    assert len(rows) == 20 and len(sql_cases) == 1160
    ledger = rd.obj(root / "evaluation/requirements-ledger.json", provenance["input_hashes"]["evaluation/requirements-ledger.json"], "SQLite provenance.input_hashes")
    manifest = rd.obj(root / "evaluation/case-manifest.json", provenance["input_hashes"]["evaluation/case-manifest.json"], "SQLite provenance.input_hashes")
    assert len(ledger["items"]) == 57 and len(manifest["cases"]) == 58
    batch = root / "results/acquisition10-20260910/batch/runs"
    qualitative = []
    eval_records = []
    source_hashes = set()
    for row in rows:
        attempt = batch / row["planned_run"] / "attempt"
        snapshot_path = attempt / "snapshot.json"
        snapshot = rd.obj(snapshot_path, row["submission_hash"], "SQLite runs.row_json.submission_hash")
        frozen = attempt / "frozen"
        decisions_path = frozen / "DECISIONS.md"
        decisions = rd.read(decisions_path, snapshot["DECISIONS.md"], "fixed snapshot.json file hash").decode("utf-8")
        section = threshold_section(decisions)
        assert section, f"No threshold section: {row['planned_run']}"
        normalized_section = section["text"].replace(",", "").replace("_", "")
        assert "100万" in normalized_section or "1000000" in normalized_section or "999999" in normalized_section
        conflict_recorded = (any(term in normalized_section for term in ("500000", "499999", "50万"))
                             and any(term in normalized_section for term in ("100万", "1000000"))
                             and "F-006" in normalized_section)
        assert conflict_recorded == (row["condition"] == "anti")
        decision_citation = rd.citation(decisions_path, section["line_start"], section["line_end"])
        branches = []
        for rel, sha in sorted(snapshot.items()):
            if not rel.startswith("backend/") or not rel.endswith(".cs") or any(x in rel.split("/") for x in ("obj", "bin")):
                continue
            path = frozen / rel
            lines = rd.read(path, sha, "fixed snapshot.json file hash").decode("utf-8-sig").splitlines()
            for no, line in enumerate(lines, 1):
                if BRANCH.search(line) and not line.lstrip().startswith("//") and ("課長" in line or "部長" in line):
                    branches.append({"citation": rd.citation(path, no, no), "source_relative_path": rel,
                                     "line": line.strip(), "interpretation": "固定された実装ソース中の分岐。今回の実行結果ではない。"})
        assert branches, f"No actual threshold branch: {row['planned_run']}"
        expected_threshold = 500000 if row["condition"] == "anti" else 1000000
        for branch in branches:
            compact = branch["line"].replace("_", "")
            expected = ("500000", "499999") if expected_threshold == 500000 else ("1000000", "999999")
            assert any(x in compact for x in expected), f"Mixed threshold branch: {row['planned_run']}"
        log_path = attempt / "agent.stdout.log"
        log = rd.read(log_path)
        messages = saved_messages(log, rd.citation(log_path), expected_threshold)
        ref_path = attempt / "evaluation-ref.json"
        ref = rd.obj(ref_path)
        assert ref["run_id"] == row["run_id"] and ref["evaluation_id"] == row["evaluation_id"]
        assert ref["submission_hash"] == row["submission_hash"] and ref["score_version"] == row["score_version"]
        eval_dir = local_path(ref["evaluation_directory"])
        version_path = eval_dir / "version.json"
        version = rd.obj(version_path)
        assert version["sha256"] == row["score_version"]
        code_path = eval_dir / "evaluator-snapshot/tests/application.spec.ts"
        code = rd.read(code_path, version["files"]["tests/application.spec.ts"], "saved version.json files and selected score_version")
        source_hashes.add(digest(code))
        results_path = eval_dir / "results.jsonl"
        results_bytes = rd.read(results_path, ref["results_sha256"], "selected evaluation-ref.json results_sha256")
        result_rows = [json.loads(line) for line in results_bytes.splitlines() if line.strip()]
        actual_cases = sorted((x["run_id"], x["evaluation_id"], x["case_id"], x["status"]) for x in result_rows)
        assert actual_cases == [x for x in sql_cases if x[0] == row["run_id"]]
        threshold_cases = [{"evaluation_id": x["evaluation_id"], "case_id": x["case_id"], "status": x["status"]}
                           for x in result_rows if x["evaluation_id"].startswith("T-006-")]
        qualitative.append({"planned_run": row["planned_run"], "run_id": row["run_id"], "condition": row["condition"],
                            "evaluation_uuid": row["evaluation_id"], "submission_hash": row["submission_hash"],
                            "snapshot": rd.citation(snapshot_path), "selected_evaluation_ref": rd.citation(ref_path),
                            "recorded_intent": {"threshold_yen": expected_threshold, "text": section["text"], "citation": decision_citation,
                                                "explicit_ap001_conflict_recorded": conflict_recorded,
                                                "claim_scope": "提出された判断記録の記載。モデルの内心や認知過程を直接証明しない。"},
                            "static_implementation": {"threshold_yen": expected_threshold, "branches": branches,
                                                      "all_read_source_files_verified_against_snapshot": True},
                            "saved_assistant_messages": messages,
                            "saved_assistant_message_selection_status": "matched" if messages else "no_matching_visible_text_or_direct_document_write_in_selected_log",
                            "assistant_message_selection": "assistant.messageの可視contentとDECISIONS.md作成要求のみ。reasoningフィールドは選択・公開しない。",
                            "saved_outcomes": {"citation": rd.citation(results_path), "threshold_cases": threshold_cases,
                                               "raw_only": True, "validity": row["evaluation_validity"], "rescored": False}})
        eval_records.append({"planned_run": row["planned_run"], "evaluation_uuid": row["evaluation_id"],
                             "directory": eval_dir, "code": code.decode("utf-8"), "code_citation": rd.citation(code_path),
                             "results_path": results_path, "results_bytes": results_bytes, "result_rows": result_rows})
    assert len(source_hashes) == 1
    representative = next(x for x in eval_records if x["planned_run"] == "anti-009")
    code_lines = representative["code"].splitlines()
    assert "setupApp=async(amount=500000)" in code_lines[8]
    assert "who='kacho'" in code_lines[9]
    dependency_rows = []
    for item in ledger["items"]:
        eid = item["evaluation_id"]
        line_nos = [no for no, text in enumerate(code_lines, 1) if eid in text]
        assert line_nos, eid
        group = "direct_threshold" if eid in DIRECT else "downstream_threshold" if eid in DOWNSTREAM else "other"
        refs = [{**representative["code_citation"], "line_start": n, "line_end": n} for n in line_nos]
        if group == "downstream_threshold":
            refs.append({**representative["code_citation"], "line_start": 9, "line_end": 10})
            if eid in {"T-013-01", "T-015-01"}:
                refs.append({**representative["code_citation"], "line_start": 46, "line_end": 46})
        if group == "direct_threshold":
            explanation = "100万円未満かつ50万円以上の入力で課長を期待。T-006-05はlowerとupperの両成功で1点。"
        else:
            explanation = EXPECTED_ROLE.get(eid, "今回定義した閾値の直接評価・課長前提の後続経路には分類しない。無影響を証明する分類ではない。")
        dependency_rows.append({"evaluation_id": eid, "feature_id": "F-" + eid[2:5],
                                "title": item["title"], "category": item["category"], "dependency_group": group,
                                "explanation": explanation, "saved_v6_source_references": refs,
                                "uses_500000_setup_but_assertion_role_invariant": eid in {"T-009-02", "T-010-03"},
                                "classification_kind": "事後の機序分析。採点・責任裁定の変更ではない。"})

    private_cases = []
    for eid, appid in (("T-011-01", 58), ("T-014-01", 64)):
        trace_path = representative["directory"] / f"browser/application-{eid}/trace.zip"
        trace_bytes = rd.read(trace_path)
        facts = []
        with zipfile.ZipFile(io.BytesIO(trace_bytes)) as archive:
            for member in sorted(x for x in archive.namelist() if x.endswith(".network")):
                for lineno, line in enumerate(archive.read(member).splitlines(), 1):
                    event = json.loads(line)
                    snap = event.get("snapshot", {})
                    request, response = snap.get("request", {}), snap.get("response", {})
                    url = request.get("url", "")
                    if request.get("method") != "POST" or not any(url.endswith(s) for s in ("/api/applications", f"/applications/{appid}/submit", f"/applications/{appid}/reject")):
                        continue
                    bodies = []
                    for part in (request.get("postData", {}), response.get("content", {})):
                        text = part.get("text")
                        resource = part.get("_sha1")
                        if resource and "resources/" + resource in archive.namelist():
                            body = archive.read("resources/" + resource)
                            text = body.decode("utf-8")
                        else:
                            body = (text or "").encode("utf-8")
                        try:
                            parsed = json.loads(text) if text else {}
                        except json.JSONDecodeError:
                            parsed = {}
                        selected = {k: parsed[k] for k in ("amount", "approverName", "message") if k in parsed}
                        bodies.append({"selected_fields": selected, "resource_member": "resources/" + resource if resource else None,
                                       "resource_sha256": digest(body)})
                    facts.append({"member": member, "line": lineno, "method": "POST",
                                  "url_path": url.split(":5173", 1)[-1], "status": response.get("status"),
                                  "request": bodies[0], "response": bodies[1]})
        assert any(x["response"]["selected_fields"].get("approverName") == "部長 次郎" for x in facts)
        if eid == "T-011-01":
            assert any(x["status"] == 403 and x["response"]["selected_fields"].get("message") == "この申請書を差し戻す権限がありません" for x in facts)
        rawcase = next(x for x in representative["result_rows"] if x["evaluation_id"] == eid)
        raw_lineno = next(n for n, line in enumerate(representative["results_bytes"].splitlines(), 1) if json.loads(line)["evaluation_id"] == eid)
        mail_summary = None
        measurement_summary = None
        for att in rawcase["evidence"]["attachments"]:
            if att.get("name") == "measurement":
                m = json.loads(base64.b64decode(att["body"]))
                measurement_summary = {k: m[k] for k in ("responsibility", "stage", "cause", "business_assertion_reached", "root_event")}
            if eid == "T-014-01" and att.get("name") == "mail-observations":
                m = json.loads(base64.b64decode(att["body"]))
                mails = []
                for key, entry in m["blobs"].items():
                    mail_bytes = base64.b64decode(entry["base64"])
                    assert digest(mail_bytes) == key
                    mail = json.loads(mail_bytes)
                    mails.append({"blob_sha256": key, "to": mail["to"], "subject": mail["subject"],
                                  "sent_at": mail.get("sentAt"), "body_published": False})
                assert len(mails) == 1 and mails[0]["to"] == "bucho@example.com"
                mail_summary = {"attachment_name": "mail-observations", "saved_reads": len(m["reads"]),
                                "mails": mails, "expected_recipient_in_saved_test": "kacho@example.com"}
        summary = ("保存ネットワークには50万円提出→部長割当→課長からの差し戻し403が残る。差し戻し成功メッセージの不在だけを機能欠如と扱えない。"
                   if eid == "T-011-01" else "保存メールは部長宛に実在し、評価は課長宛を期待した。メール生成の欠如ではなく、閾値に伴う宛先の相違を確認できる。")
        private_cases.append({"planned_run": "anti-009", "run_id": next(r["run_id"] for r in rows if r["planned_run"] == "anti-009"),
                              "evaluation_uuid": representative["evaluation_uuid"], "evaluation_id": eid,
                              "trace": rd.citation(trace_path), "network_facts": facts,
                              "saved_case": rd.citation(representative["results_path"], raw_lineno),
                              "raw_status": rawcase["status"], "saved_measurement": measurement_summary,
                              "mail_summary": mail_summary, "interpretation": summary,
                              "claim_limit": "この保存ケースの機序証拠。全非合格の責任を裁定せず、raw点・旧裁定を変更しない。"})

    source_db = rd.citation(db)
    outputs = {
        "qualitative.json": {"schema_version": 1, "source_database": source_db, "runs": qualitative,
                              "counts": {"runs": 20, "anti_recorded_conflict_and_500000_branch": 10, "normal_1000000_branch": 10},
                              "new_observations": 0, "rescoring": False},
        "dependency-map.json": {"schema_version": 1, "source_database": source_db,
                                 "ledger": rd.citation(root / "evaluation/requirements-ledger.json"),
                                 "case_manifest": rd.citation(root / "evaluation/case-manifest.json"),
                                 "saved_evaluator_sha256": rows[0]["score_version"],
                                 "all_twenty_saved_application_specs_sha256": next(iter(source_hashes)),
                                 "saved_source_versions_verified": [{"planned_run": x["planned_run"], "evaluation_uuid": x["evaluation_uuid"], **x["code_citation"]} for x in eval_records],
                                 "groups": {"direct_threshold": 3, "downstream_threshold": 10, "other": 44},
                                 "items": dependency_rows,
                                 "invariants": ["57評価ID・58ケース・等配点を維持", "T-006-05の両ケース成功で1点", "13IDの除外集計は感度分析であり修正採点ではない", "case statusから責任のimplementation分類を作らない"]},
        "private-evidence-index.json": {"schema_version": 1, "cases": private_cases,
                                        "private_bodies_copied": False, "new_observations": 0,
                                        "read_method": "既存ZIP内のネットワークJSONと保存results.jsonlの添付をメモリ上で読む。アプリ・ブラウザ・評価器を起動しない。"},
    }
    assert len(dependency_rows) == 57
    assert all(sum(x["dependency_group"] == g for x in dependency_rows) == n for g, n in outputs["dependency-map.json"]["groups"].items())
    # End-to-end check catches changes after a file's initial before/after read pair.
    for path, record in rd.records.items():
        current = digest(Path(path).read_bytes())
        assert current == record["sha256_before"], f"Original changed before output: {path}"
        record["sha256_at_collection_end"] = current
    out_hashes = {name: write_output(output / name, obj) for name, obj in outputs.items()}
    receipt = {"schema_version": 1, "originals_unchanged": True, "files_read": len(rd.records),
               "read_operations": sum(x["read_count"] for x in rd.records.values()),
               "all_twenty_snapshots_and_selected_evaluations_matched": True,
               "source_reads": [rd.records[k] for k in sorted(rd.records)],
               "output_sha256": out_hashes, "script_sha256": digest(Path(__file__).read_bytes()),
               "new_observations": 0, "model_calls": 0, "rescoring": False,
               "scope": "原本の読取と既存証拠の分析。hash照合はファイル単位であり、未読ファイルへの追加検証を意味しない。"}
    write_output(output / "collection-verification.json", receipt)
    print(json.dumps({"runs": 20, "dependency_ids": 57, "private_examples": 2,
                      "files_read": len(rd.records), "originals_unchanged": True,
                      "outputs": list(out_hashes) + ["collection-verification.json"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

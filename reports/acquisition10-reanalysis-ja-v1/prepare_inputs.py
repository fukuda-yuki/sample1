"""Copy existing observations only. Never launch an observer, application, or model."""
from pathlib import Path
import hashlib, json, shutil, sqlite3, uuid
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent.parent
OLD = ROOT / "reports/acquisition10-preserve-first-20260910"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    manifest_path = BASE / "source-manifest.json"
    if manifest_path.exists():
        raise SystemExit("Inputs already fixed; use rebuild.py for computation only.")
    source = BASE / "source"
    source.mkdir(exist_ok=True)
    old_inventory = {str(p.relative_to(OLD)): digest(p) for p in sorted(OLD.rglob("*")) if p.is_file()}
    names = ["analysis.sqlite", "retention.json", "planned-runs.json",
             "measurement-profile.json", "evaluation-coverage.json",
             "verification.json", "source-notes.md", "summary.json"]
    originals = {name: OLD/name for name in names}
    originals.update({"requirements-ledger.json": ROOT/"evaluation/requirements-ledger.json",
                      "case-manifest.json": ROOT/"evaluation/case-manifest.json",
                      "normal-spec.md": ROOT/"normal/spec.md", "anti-spec.md": ROOT/"anti/spec.md"})
    entries = []
    for name, path in originals.items():
        before = digest(path)
        shutil.copyfile(path, source/name)
        assert before == digest(path) == digest(source/name)
        entries.append({"copy": "source/"+name, "original": str(path), "sha256": before})
    with sqlite3.connect((source/"analysis.sqlite").as_uri()+"?mode=ro&immutable=1", uri=True) as db:
        prov = json.loads(db.execute("SELECT document_json FROM provenance").fetchone()[0])
        for name in ("requirements-ledger.json", "case-manifest.json"):
            assert digest(source/name) == prov["input_hashes"]["evaluation/"+name]
    write(manifest_path, {"analysis_id": str(uuid.uuid4()),
                         "created_at": datetime.now(timezone.utc).isoformat(),
                         "experiment_id": prov["experiment_id"],
                         "inputs": entries,
                         "old_report_directory": str(OLD),
                         "old_report_inventory": old_inventory})
    write(BASE/"analysis-policy.json", {
        "analysis_id": json.loads(manifest_path.read_text())["analysis_id"],
        "authorization": "User approved the reanalysis plan in this task.",
        "token_policy": "All 20 observed_tokens sums are accepted as confirmed whole-Run totals for this report.",
        "source_flags_unchanged": True,
        "formal_scoring_unchanged": "57 equally weighted IDs; T-006-05 requires both cases.",
        "new_observations": False, "new_evaluations": False,
        "unit": "Run", "paired_unit": "fixed original pair",
        "bootstrap": {"seed": 20260910, "replicates": 20000, "interval": "percentile 95%"},
        "selection": "All 20 acquired Runs; supplementary subsets are labeled sensitivity analyses.",
        "dependency_coding": "Post-hoc static reading of the retained v6 evaluator; not a rescoring or causal attribution.",
        "primary_artifact": "Japanese Markdown, as explicitly approved; PNG and SVG scientific figures.",
    })
    print(json.dumps({"copied_inputs": len(entries), "old_report_files": len(old_inventory),
                      "analysis_id": json.loads(manifest_path.read_text())["analysis_id"]}))

if __name__ == "__main__":
    main()

"""Verify copied-input reproduction and unchanged originals without new observation."""
from pathlib import Path
import argparse, hashlib, json, os, re, runpy, shutil, sqlite3, subprocess, sys
from urllib.parse import unquote

BASE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding="utf-8"))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def worker():
    denied=[Path(p).resolve() for p in read(BASE/"denied-roots.json")]
    probes=0
    def check(value):
        if not isinstance(value,(str,bytes,os.PathLike)):return
        raw=os.fsdecode(value)
        if raw.startswith("file:"):raw=unquote(raw[5:].split("?")[0])
        path=Path(raw).resolve()
        if any(path==d or d in path.parents for d in denied):
            raise PermissionError("Original input access denied in copied-input reproduction.")
    def audit(event,args):
        if event in ("open","sqlite3.connect"):check(args[0])
    sys.addaudithook(audit)
    for root in denied:
        target=root/"analysis.sqlite"
        for action in (lambda p=target:p.open("rb"),
                       lambda p=target:sqlite3.connect(str(p)),
                       lambda p=target:sqlite3.connect(p.as_uri()+"?mode=ro",uri=True)):
            try:action()
            except PermissionError:probes+=1
            else:raise AssertionError("Access guard probe did not reject original path")
    sys.path.insert(0,str(BASE))
    from rebuild import build
    from write_report import main as report
    from build_notebook import main as notebook
    build(BASE);report(BASE);notebook(BASE)
    sys.argv=[str(BASE/"render_figures.py"),"--data",str(BASE/"analysis-results.json"),
              "--output",str(BASE/"figures")]
    runpy.run_path(str(BASE/"render_figures.py"),run_name="__main__")
    write(BASE/"copied-input-check.json",{"denial_probes":probes,"denied_roots":list(map(str,denied)),
      "all_computation_finished":True,"scope":"Python open and SQLite audit guard, not OS-level air gap.",
      "new_observations":False,"new_evaluations":False})

def verify():
    manifest=read(BASE/"source-manifest.json")
    old=Path(manifest["old_report_directory"])
    inputs={Path(x["original"]):x["sha256"] for x in manifest["inputs"]}
    inputs.update({old/name:sha for name,sha in manifest["old_report_inventory"].items()})
    evidence=read(BASE/"evidence/collection-verification.json")
    inputs.update({Path(x["path"]):x["sha256_before"] for x in evidence["source_reads"]})
    for p,sha in inputs.items():assert digest(p)==sha,str(p)
    root=BASE.parent.parent
    clone=root/"results"/("reanalysis-ja-v1-reproduction-"+manifest["analysis_id"])
    clone.mkdir(parents=True,exist_ok=False)
    shutil.copytree(BASE/"source",clone/"source")
    shutil.copytree(BASE/"evidence",clone/"evidence")
    for name in ("source-manifest.json","analysis-policy.json","queries.sql","rebuild.py","write_report.py",
                 "build_notebook.py","render_figures.py","verify_delivery.py"):
        shutil.copyfile(BASE/name,clone/name)
    denied=[BASE,old,root/"results/acquisition10-20260910",
            root.parent/"sample1-private-eval-linux",Path("/mnt/c/Users/mwam0/ResearchArchives/sample1"),
            root/"scripts",root/"analysis",root/"evaluation",root/"normal",root/"anti"]
    write(clone/"denied-roots.json",list(map(str,denied)))
    with (clone/"worker.log").open("w") as log:
        completed=subprocess.run([sys.executable,"-B",str(clone/"verify_delivery.py"),"--worker"],
                                 cwd=clone,stdout=log,stderr=subprocess.STDOUT)
    if completed.returncode:raise RuntimeError("Copied-input worker failed; see "+str(clone/"worker.log"))
    names=["analysis.sqlite","analysis-results.json","report.md","claims.md","claims.json","claims.csv",
           "analysis.ipynb","notebook-verification.json","calculation-verification.json"]
    names += [str(p.relative_to(BASE)) for p in sorted((BASE/"tables").glob("*.csv"))]
    names += [str(p.relative_to(BASE)) for p in sorted((BASE/"figures").iterdir()) if p.suffix in (".png",".svg")]
    comparisons=[]
    for name in names:
        original_hash=digest(BASE/name);copy_hash=digest(clone/name)
        assert original_hash==copy_hash,name
        comparisons.append({"file":name,"sha256":original_hash,"copied_rebuild_identical":True})
    for p,sha in inputs.items():assert digest(p)==sha,str(p)
    after={str(p.relative_to(old)):digest(p) for p in old.rglob("*") if p.is_file()}
    assert after==manifest["old_report_inventory"]
    figure_qa=read(BASE/"figures/visual-verification.json")
    assert figure_qa["source_data_sha256"]==digest(BASE/"analysis-results.json")
    for f in figure_qa["figures"]:
        for x in f["files"]:assert digest(BASE/x["path"])==x["sha256"]
    for name,sha in evidence["output_sha256"].items():assert digest(BASE/"evidence"/name)==sha
    assert digest(BASE/"evidence/collect_evidence.py")==evidence["script_sha256"]
    # Pattern inspection does not fetch or read any credential.
    secret_pattern=re.compile(r"(?<!\w)(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9]{24,}|AKIA[0-9A-Z]{16})")
    inspected=0
    for p in BASE.rglob("*"):
        if not p.is_file():continue
        assert p.suffix not in (".zip",".sse",".ts",".tsx"),str(p)
        if p.suffix in (".json",".jsonl",".md",".csv",".py",".sql",".ipynb",".txt"):
            inspected+=1
            assert not secret_pattern.search(p.read_text(encoding="utf-8-sig")),str(p)
    expected_after_success={"validation.md","verification.json"}
    for p in BASE.glob("*.md"):
        for match in re.finditer(r"\]\(([^)]+)\)",p.read_text(encoding="utf-8")):
            target=match.group(1).split("#")[0]
            if not target or re.match(r"^[A-Za-z]+:",target):continue
            assert (p.parent/target).exists() or target in expected_after_success,(p,target)
    record={"analysis_id":manifest["analysis_id"],"original_files_checked":len(inputs),
      "originals_unchanged":True,"old_report_files_unchanged":len(after),
      "source_sqlite_sha256":digest(BASE/"source/analysis.sqlite"),
      "copied_input_reproduction":read(clone/"copied-input-check.json"),
      "reproduction_directory":str(clone),"identical_outputs":comparisons,
      "secret_pattern_files_checked":inspected,"secret_pattern_matches":0,"credential_values_accessed":False,
      "all_local_report_links_resolved":True,"all_16_figure_hashes_verified":True,
      "new_observations":False,"new_evaluations":False}
    write(BASE/"verification.json",record)
    validation=f"""# 検証結果

## 判定：記載した限界を伴う分析として提出可能

- 全20 Run、各条件10件、1,140 Run×ID、1,160ケースをSQLで照合。
- 元の5テーブル、得点、提出hash、旧usageフラグ、旧裁定を保持。
- 新しい確定総量は134,321,987トークン。
- 旧レポート{len(after)}ファイルと参照原本を含む{len(inputs)}ファイルのSHA256が作業前後で一致。
- コピーした入力とコードだけから、SQLite・数表・本文・Notebook・図を再生成。{len(comparisons)}出力すべてのバイト列が一致。
- 再生成中は旧レポート・旧Run・非公開評価・archive・元管理コードへのPython/SQLiteアクセスを拒否。{record["copied_input_reproduction"]["denial_probes"]}件の拒否プローブが成功。OSレベルの隔離とは区別。
- Notebookの実際のPython/SQLコード8セルを先頭から実行し、全セル成功。Jupyterカーネルや画面を起動した検証ではないことを実行記録に明記。
- 日本語図8系列を実画像で確認。PNG/SVG計16ファイルのhash・SVG文字path化を確認。
- 独立した読解レビューで、主張・数値・分母・因果解釈に実質的な誤りなし。図ごとの配色説明を修正済み。
- 公開用テキスト{inspected}ファイルで秘密情報候補パターン検出0件。鍵の値は参照していない。非公開評価コード・画像・trace本体は含めていない。
- 観測機、モデル、実装アプリ、評価器の再実行なし。

## 解釈上の限界

充足率は既存v6の結果で、品質全般を確定した値ではありません。13 IDへの集中率はスコア差の算術上の所在であり、因果寄与率や修正後の回復点数ではありません。bootstrapは10ペアのRun間変動を表し、評価器の系統的な制約を補正しません。

[機械可読の検証記録](verification.json)・[計算検証](calculation-verification.json)・[Notebook実行](notebook-verification.json)・[図の検証](figures/visual-verification.json)・[原本読取照合](evidence/collection-verification.json)
"""
    (BASE/"validation.md").write_text(validation,encoding="utf-8")
    print(json.dumps({"unchanged_originals":len(inputs),"identical_outputs":len(comparisons),
                      "reproduction_probes":record["copied_input_reproduction"]["denial_probes"]}))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--worker",action="store_true")
    args=parser.parse_args()
    worker() if args.worker else verify()

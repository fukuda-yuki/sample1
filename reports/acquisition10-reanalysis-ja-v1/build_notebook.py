"""Build and execute a portable notebook of plain Python/SQL cells.

No kernel packages are needed by this executor; no IPython magics are used.
Each code cell is actually executed in order in one Python namespace, and its
stdout is retained in a valid nbformat 4.5 document. No observer is invoked.
"""
from pathlib import Path
import argparse, contextlib, hashlib, io, json, os, platform

BASE=Path(__file__).resolve().parent
def main(output):
    cells=[]
    def md(text):cells.append(dict(cell_type="markdown",metadata={},source=text))
    def code(text):cells.append(dict(cell_type="code",metadata={},source=text,execution_count=None,outputs=[]))
    md("""# 既存20 RunのSQL再分析

## 要点

不整合条件は平均総トークンが約11.6%少ない一方、合格IDあたり投入量は約37.8%多い。
閾値直接・後続依存13 IDに合格数差の62.5%が集中するが、因果寄与率ではない。
本文の考察と保存証拠は report.md と claims.md を参照。

## 文脈と方法

全20 Runを保持し、observed_tokensを本報告の確定総量として採用する。
旧raw点・旧usageフラグ・旧裁定は変更しない。推論単位はRun、対応単位は固定10ペア。
新規観測・モデル呼出し・再採点は一切行わない。
""")
    md("## データ\n\n### 1. 同じフォルダのSQLiteを読み取り専用で開く")
    code("""from pathlib import Path
import sqlite3, json, hashlib, numpy as np
from rebuild import query_map, rank
base=Path.cwd()
db=sqlite3.connect((base/'analysis.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
db.row_factory=sqlite3.Row
queries=query_map()
def query(name): return [dict(r) for r in db.execute(queries[name])]
runs=query('runs'); pairs=query('pairs')
assert len(runs)==20 and len(pairs)==10
assert sum(r['total_tokens'] for r in runs)==134321987
print({'Run数':len(runs),'ペア数':len(pairs),'確定総トークン':sum(r['total_tokens'] for r in runs)})
""")
    md("### 2. 元ケースから57 IDの得点を再構成する")
    code("""scores={}
for row in db.execute("SELECT run_id,evaluation_id,MIN(status='pass') passed,COUNT(*) n FROM case_results GROUP BY run_id,evaluation_id"):
    scores.setdefault(row['run_id'],[]).append((row['evaluation_id'],row['passed'],row['n']))
assert sum(len(s) for s in scores.values())==1140
assert db.execute('SELECT COUNT(*) FROM case_results').fetchone()[0]==1160
for r in runs:
    assert len(scores[r['run_id']])==57
    assert sum(s[1] for s in scores[r['run_id']])==r['passed']
    assert next(s[2] for s in scores[r['run_id']] if s[0]=='T-006-05')==2
print({'再構成したRun×ID':1140,'元ケース':1160,'T00605の両ケース規則':'一致'})
""")
    md("## 結果\n\n### 3. 全20件の総量と適合効率")
    code("""summary=[]
for condition in ('normal','anti'):
    rr=[r for r in runs if r['condition']==condition]
    summary.append({'condition':condition,'n':len(rr),'tokens':sum(r['total_tokens'] for r in rr),
                    'passed':sum(r['passed'] for r in rr)})
n,a=summary
relative_tokens=a['tokens']/n['tokens']-1
relative_cost=(a['tokens']/a['passed'])/(n['tokens']/n['passed'])-1
assert n['tokens']==71287304 and a['tokens']==63034683
assert n['passed']==402 and a['passed']==258
print(summary)
print({'トークン相対差':round(relative_tokens,6),'合格IDあたり投入相対差':round(relative_cost,6)})
""")
    md("### 4. 判断記録・固定分岐と、依存群の合格数")
    code("""print(query('interpretations'))
groups=query('groups')
normal={r['dependency_group']:r['passed_ids'] for r in groups if r['condition']=='normal'}
anti={r['dependency_group']:r['passed_ids'] for r in groups if r['condition']=='anti'}
gaps={k:normal[k]-anti[k] for k in normal}
assert gaps=={'direct_threshold':30,'downstream_threshold':60,'other':54}
assert (gaps['direct_threshold']+gaps['downstream_threshold'])/sum(gaps.values())==0.625
print({'群別合格数差':gaps,'13IDへの集中割合':0.625})
""")
    md("### 5. ペアを維持したbootstrapと1ペア除外")
    code("""diff=np.array([[p['token_difference'],p['score_difference_pp']] for p in pairs])
indices=np.random.default_rng(20260910).integers(0,10,size=(20000,10))
interval=np.quantile(diff[indices].mean(axis=1),[.025,.975],axis=0)
loo=np.array([np.delete(diff,i,axis=0).mean(axis=0) for i in range(10)])
assert np.all(loo[:,1]<0)
print({'平均差':diff.mean(axis=0).tolist(),'95%区間_下上':interval.tolist(),
       '1ペア除外_得点差範囲':[float(loo[:,1].min()),float(loo[:,1].max())]})
""")
    md("### 6. 条件内の相関と観測された反例")
    code("""for condition in ('normal','anti'):
    rr=[r for r in runs if r['condition']==condition]
    xs=[r['total_tokens'] for r in rr];ys=[r['passed'] for r in rr]
    print(condition,{'Pearson':round(float(np.corrcoef(xs,ys)[0,1]),3),
                     'Spearman':round(float(np.corrcoef(rank(xs),rank(ys))[0,1]),3)})
print({'観測上の非劣位点':[r['planned_run'] for r in query('pareto')]})
""")
    md("### 7. 応答回数と旧抽出・実行時期の感度")
    code("""print(query('process'))
print(query('http_groups'))
for label,selected in [('前半',pairs[:5]),('後半',pairs[5:])]:
    print(label,{'n':len(selected),'平均トークン差':sum(r['token_difference'] for r in selected)/len(selected),
                '平均合格ID差':sum(r['passed_difference'] for r in selected)/len(selected)})
""")
    md("### 8. コピーした元SQLiteとの原データ一致")
    code("""original=sqlite3.connect((base/'source/analysis.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
for table in ('runs','case_results','telemetry_refs','evaluations','provenance'):
    assert sorted(map(tuple,db.execute('SELECT * FROM '+table)))==sorted(original.execute('SELECT * FROM '+table))
print({'元5テーブル':'一致','元SQLite_SHA256':hashlib.sha256((base/'source/analysis.sqlite').read_bytes()).hexdigest()})
original.close();db.close()
""")
    md("""## 考察

- 矛盾の記録と詳細仕様優先が両立している。気づかなかったという説明とは区別する。
- 閾値依存群への失点集中は保存された操作経路と整合するが、因果寄与率ではない。
- 全件での消費量比較は、達成度・ばらつき・順序感度と併せて解釈する。
- 図と具体的trace事例、反証・限界を含む解釈は report.md にある。

![総トークンと項目充足率](figures/03-token-score.png)
""")
    namespace={"__name__":"__notebook__"}
    import sys
    prior=Path.cwd();sys.path.insert(0,str(output))
    executed=0
    try:
        os.chdir(output)
        for i,cell in enumerate(cells):
            cell["id"]=hashlib.sha256((str(i)+cell["source"]).encode()).hexdigest()[:12]
            if cell["cell_type"]=="code":
                stream=io.StringIO()
                with contextlib.redirect_stdout(stream):
                    exec(compile(cell["source"],f"analysis.ipynb:cell-{i+1}","exec"),namespace)
                executed+=1;cell["execution_count"]=executed
                cell["outputs"]=[{"output_type":"stream","name":"stdout","text":stream.getvalue()}]
    finally:os.chdir(prior);sys.path.pop(0)
    notebook={"nbformat":4,"nbformat_minor":5,"metadata":{
      "kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
      "language_info":{"name":"python","version":platform.python_version()},
      "execution_method":"Plain Python/SQL cells executed in sequence in one namespace; no IPython magics or Jupyter frontend used."},
      "cells":cells}
    assert len({c["id"] for c in cells})==len(cells)
    assert executed==8
    for c in cells:
        assert c["cell_type"] in ("markdown","code") and isinstance(c["source"],str)
        if c["cell_type"]=="code":
            assert isinstance(c["execution_count"],int)
            assert all(o["output_type"]=="stream" and isinstance(o["text"],str) for o in c["outputs"])
    def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write(output/"analysis.ipynb",notebook)
    write(output/"notebook-verification.json",{"executed_code_cells":executed,"all_passed":True,
      "method":"Sequential execution of actual plain Python cells with captured stdout; nbformat 4.5 structural checks.",
      "jupyter_kernel_or_frontend_run":False,"ipython_magics":False,"new_observations":False})
    print(json.dumps({"executed_cells":executed,"notebook":str(output/"analysis.ipynb")}))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=BASE)
    args=parser.parse_args();main(args.output.resolve())

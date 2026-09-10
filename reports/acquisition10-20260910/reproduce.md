# この提出物の再集計・再採点

対象Runは `256a2bf5-a8db-4a43-81bc-17bc38eda0d3`、提出snapshot hashは `f21b262efb7e3e444d3bb9cc2176ccdc45cb4b501d6ebe3e9076cda047cbcd6a`。初回評価UUIDは `55cb359f-b3d4-4718-9ff0-7d22e8a8d291`。公開Gitには非公開評価器・画面・traceを含めません。研究者権限の独立保管庫が必要です。

## 保存済み結果の再集計

`analysis-reference.json`に記載された不変パッケージを使います。管理コードは取得時commit `3769176e425de9077e8012331ffd16e644be3180`、Python 3.12、分析環境matplotlib 3.10.8で検証しました。既存出力先を使い回さず、復元先を元データのディレクトリ外へ置いてください。

```sh
python scripts/copilot_analysis_archive.py restore \
  /mnt/c/Users/mwam0/ResearchArchives/sample1 \
  reports/acquisition10-20260910/analysis-reference.json \
  /research/new-restoration

python /research/new-restoration/payload/management/scripts/copilot_batch.py export \
  /research/new-restoration/payload/batch \
  --validity /research/new-restoration/payload/validity.json \
  --restoration-map /research/new-restoration/restoration-map.json
```

CSV/JSONのhashとSQLiteの5テーブルの行一致で検証します。SQLiteファイル全体のbyte一致を論理一致と混同しません。今回、元データ・元評価保管先・archive・元管理コードへのPython open/SQLiteアクセスを拒否するaudit hookを使い、復元物だけからのCSV、JSON、5テーブルの一致を確認しました。これは別マシンやOS全体のアクセス制限を検証したという意味ではありません。証拠は `verification.json`。

## 新しい基準で再採点

1. `verification.json`内のRun原本・評価原本・runtimeの参照から、新規ディレクトリへ復元する。snapshotと全固定ソース・lockfileのhashを照合する。mutableなworking/node_modulesを提出物として使わない。
2. 新しい評価版のソース・台帳・設定・lockfile・imageを固定する。初回v6のevaluator-snapshot、raw結果、裁定台帳はそのまま残す。
3. `evaluation/prepare-app-container.py <復元Run> <新評価器root> --evaluator-image <固定image>`で独立DB・アプリを準備し、新評価UUIDを記録する。返されたresearcherコンテナを実行し、準備・画面・trace・結果・終了回収を保存する。Runの生成物は修正しない。
4. 新評価UUIDと旧Run UUID・同一提出hash・新評価版・summary/results hashを新しい妥当性台帳へ追加する。実際のUI証拠を確認してvalid/invalid/pendingを裁定し、旧裁定を上書きしない。
5. 新評価を選んだ別のselection JSONを作る。旧選択も保持し、`analysis/collect_runs.py <selection.json> <新出力先> --validity <新台帳> --ledger <新評価の固定台帳>`で再集計する。これは開始済み1件の再採点であり、新たな実装Runや19枠の補充ではない。
6. 新評価・裁定・選択・集計を追加パッケージとして保存し、復元検証する。評価基準が変わった数値を今回のv6比較に混ぜない。

現時点ではこの再採点を実施していません。完了宣言後の停止と親span欠落は[Issue #45](https://github.com/fukuda-yuki/sample1/issues/45)、v6操作制約は[Issue #46](https://github.com/fukuda-yuki/sample1/issues/46)に残しています。

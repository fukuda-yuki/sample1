# 取得データの復元・再集計・再採点

対象はexperiment UUID `dcacece4-120a-4258-bbd8-c09940dbb67c` の固定20枠です。Run UUID、提出snapshot hash、初回評価UUID、計測処理UUIDは `runs.json` と `retention.json` で対応します。原本は `C:\Users\mwam0\ResearchArchives\sample1` にあります。公開Gitには非公開評価器・画面・traceを含めません。

公開集計の確認には、同じフォルダを作業ディレクトリにして `analysis-checks.ipynb` のコードセルを上から実行します。モデルや非公開評価器を呼ばず、JSONとSQLiteの20枠、Run参照、57 ID・58ケース、条件・モデル別統計、欠測を検査します。配布Notebookには実際に実行した出力を保存しています。

図は同じフォルダで `python render_delivery_plots.py .` を実行すると、公開`runs.json`から再生成できます。総tokenの分布、総token×有効品質、総token×raw v6結果の3図です。品質nullをゼロの点として描きません。`input_tokens`・`output_tokens`は旧投影の列なので、新しい`total_tokens`の再計算へ混用しないでください。列の出典は`source-notes.md`に記載しています。

## 保存済み結果を再集計する

`analysis-reference.json` が指す不変パッケージから、新規ディレクトリへ復元します。元データの配下に復元先を作らないでください。Python 3.12、matplotlib 3.10.8で検証しています。管理ソースはパッケージ内にも保持しています。

```sh
python scripts/copilot_analysis_archive.py restore \
  /mnt/c/Users/mwam0/ResearchArchives/sample1 \
  reports/acquisition10-preserve-first-20260910/analysis-reference.json \
  /research/new-restoration

python /research/new-restoration/payload/management/scripts/copilot_batch.py export \
  /research/new-restoration/payload/batch \
  --validity /research/new-restoration/payload/validity.json \
  --restoration-map /research/new-restoration/restoration-map.json
```

CSV/JSONのhashとSQLiteの `runs`、`case_results`、`telemetry_refs`、`evaluations`、`provenance` の行を比較します。SQLiteのファイルbyte一致と論理一致は別です。今回の復元検証では、元データ・元評価・archive・元管理コードへのPython file-open/SQLiteアクセスを拒否し、復元物だけで一致するか確認しています。これは別マシンやOS全体のアクセス制限の検証ではありません。実際の成否と参照hashは `verification.json` に記録します。

既存の復元検証では、一部の評価原本ディレクトリが拒否対象から漏れていました。今回の最終確認では`strict_restored_export.py`で制限を補い、全評価原本の場所を保存済み`evaluation-locations.json`から自動で拒否対象へ追加しています。通常のファイルopen、SQLiteのpath指定とfile URI指定を拒否し、既存の集計も参照せずにexportします。結果は`strict-isolation.json`です。旧検証記録は上書きしていません。

```sh
python strict_restored_export.py /research/new-restoration /research/new-check \
  --forbid /old/project/results/acquisition10-20260910 \
  --forbid /old/private-evaluator \
  --forbid /old/archive \
  --forbid /old/project/scripts \
  --forbid /old/project/analysis \
  --forbid /old/project/config \
  --forbid /old/project/evaluation \
  --forbid /old/export
```

`--forbid`は実際の元データ・管理コード・既存集計のパスへ置き換えます。復元先と新しい出力先を拒否対象に含めないでください。`new-check/export`のCSV/JSONとSQLiteを比較対象へ加えます。今回実際に拒否したパスと照合結果は`strict-isolation.json`で確認できます。

## 計測器を更新する

1. 対象Runを新しい場所へ復元し、固定ソースとsnapshot、usage原本、native telemetryのhashを照合します。`working/node_modules` は提出物ではありません。
2. 元の `usage.json`、`telemetry-link.json`、`measurements/<UUID>/measurement.json`、選択参照を保持します。新しい処理コードを固定し、新しい処理UUIDのディレクトリへ出力します。
3. gateway開始・終端・usage、native call対応、親span構造、monitor読戻しを独立して評価します。親span欠落だけでgateway合計を消さず、未観測tokenをゼロにしません。処理版・入力hash・欠測理由を記録します。
4. 新しい計測を選ぶ参照と、その選択理由・時刻を別記録に追加します。旧参照も保存します。元のRun UUIDと提出hashは変えません。
5. 新処理・選択・集計を追加パッケージとして保管し、復元して照合します。今回の報告値を黙って書き換えません。

## 新しい基準で再採点する

1. `retention.json` の原本・評価原本と、分析パッケージ内の評価環境から新規ディレクトリへ復元します。全固定ソース・lockfileと提出snapshot hashを照合します。
2. 新評価器のソース・台帳・設定・lockfile・imageを固定します。v6のraw結果、evaluator-snapshot、妥当性台帳、裁定を残します。
3. `evaluation/prepare-app-container.py <復元Run> <新評価器root> --evaluator-image <固定image>` で独立DB・アプリを準備します。新評価UUIDを記録し、返されたresearcherコンテナを実行します。準備・画面・trace・結果・停止回収を保存します。生成物は修正しません。
4. 新評価UUID、旧Run UUID、同一提出hash、新評価版、summary/results hashを新しい妥当性台帳へ追加します。通常UIの操作証拠に基づいてvalid/invalid/pendingを裁定し、実装原因・評価側判定不能・未到達を区別します。
5. 新評価を指定する別selection JSONを作ります。旧選択も保持し、`analysis/collect_runs.py <selection.json> <新出力先> --validity <新台帳> --ledger <新評価の固定台帳>` で再集計します。これは同一提出物の再採点であり、新しい実装Runや枠の補充ではありません。
6. 新評価・裁定・選択・集計を追加保管し、復元して照合します。新評価基準による品質値を初回v6の値と混ぜません。

実行環境の再構成には `runtime-reference.json` の共通環境パッケージと各restore receiptを使用します。receiptが指す独立保管庫のパッケージを復元し、保存済みimage tarのSHAを照合してから `docker load --input <復元したtar>` で読み込みます。CLI・npm/NuGet依存・評価用Nodeと固定評価器も保存対象です。ネットから同名の最新imageを再取得して、今回の環境と同一と扱わないでください。

今回の評価アプリはinternalネットワーク上で、image内のnpm cacheを使ったofflineの`npm ci`と、外部package sourceを除いた`dotnet restore`により起動しました。復元時もこの設定と固定lockfileを使用し、ネット上の新しい依存へ差し替えません。アプリ起動の成功と業務要件の充足は別に確認します。

全Runの取得と、有効品質の確定は別の進捗です。親span・CLI終了処理は [Issue #45](https://github.com/fukuda-yuki/sample1/issues/45)、既知のv6制約は [Issue #46](https://github.com/fukuda-yuki/sample1/issues/46)、providerのtool_choice 400は [Issue #47](https://github.com/fukuda-yuki/sample1/issues/47) に記録しています。

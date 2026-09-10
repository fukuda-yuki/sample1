# 再分析・再集計・再採点の手順

[report.md](report.md)を本文の正本とし、[report.html](report.html)は同じMarkdownから生成した表示版とする。前回のレポートと原本は別の場所に保持している。

## 保存データから数値と図を再生成する

本フォルダをカレントディレクトリとして実行する。モデル、実装CLI、評価器、アプリは起動しない。

```sh
python -B analyze.py
python -B query_evidence.py
python -B render_figures.py
python -B build_supplement.py
```

初回分析には前回と同じWSL UbuntuのPython仮想環境を使う。Python 3.12.3、NumPy 2.5.3、Matplotlib 3.10.8を使用する。日本語フォントはYu Gothic。フォント位置は`REPORT_FONT`で指定でき、未指定時はWindowsのFontsフォルダを参照する。実際のフォントhashは`figures/figure-trace.json`に保存する。

`analyze.py`は`source-manifest.json`に登録された入力hashを検査し、前回・追加分のSQLiteを読み取り専用で開く。予定枠・Run UUID・提出hash・評価UUIDを照合し、57 ID・58ケースを再構成してから、派生CSV／JSON／SQLiteを出力する。`query_evidence.py`は新しい分析SQLiteに対して`queries.sql`のSELECT文を実行し、主張を点検するための実際の問い合わせ結果を保存する。

別の出力先も指定できる。

```sh
python -B analyze.py --output /path/to/replay/data
python -B query_evidence.py --database /path/to/replay/data/analysis.sqlite --output /path/to/replay/data/sql-evidence.json
python -B render_figures.py --data /path/to/replay/data/results.json --output /path/to/replay/figures
python -B build_supplement.py --data /path/to/replay/data --output /path/to/replay/supplement.md
```

## 入力と列の意味

- `source/previous/analysis.sqlite`：前回20件の保存済みDBの固定コピー。旧評価のinvalid／pendingを保持する。
- `source/additional/analysis.sqlite`：今回40予定枠の固定エクスポート。元の欠測値、起動不能時の出力、裁定を変更せず保存する。
- `data/analysis.sqlite`：累計の分析用DB。`runs`は1予定枠1行、`case_results`は評価UUID×Run×ケース、`id_results`はRun×評価ID。主キーをまたいだ同名slotでの結合は行わない。
- `recorded_total_tokens`：元の`observed_tokens`。記録がある合計を採用し、usageのない応答を推定で補完しない。
- `recorded_input_tokens`／`recorded_output_tokens`／`recorded_cached_input_tokens`：保存済みgatewayのusageから重複requestを除いて集計した内訳。大消費Runの確認を契機に加えた事後の会計分析で、入力＋出力は記録済み総トークンと照合する。キャッシュ欄に不足があれば当該内訳をnullとする。料金や思考の質を推定しない。
- `source_total_tokens`／`source_usage_complete`：元の総量・完全性フラグ。記録済み指標とは別に残す。
- `raw_end_reason`／`exit_code`／`stop_trigger`／`stop_method`／`completion_declaration_captured`：監督側の終了理由、CLI終了コード、停止トリガー、停止方法、完了宣言の検出を分けた記録。終了をアプリの合格と読み替えない。
- `source_passed_ids`：保存済みv6の元の合格ID数。起動不能時の0という出力も変更しない。
- `passed_ids`／`recorded_pass_rate`：評価を実行できた提出物の保存済み合格ID数と、57を分母とした百分率。T-006-05は2ケースとも合格した場合のみ1点。全体が評価不能の場合はnullとする。元の0やblockedの雛形を実行済みの0点に置き換えない。詳しくは[measurement-notes.md](measurement-notes.md)を参照。
- `effective_quality`／`evaluation_validity`：製品品質の確定値と評価妥当性。保存済みの合格率から自動的に有効品質へ変換しない。
- `pair_key`：取得バッチと予定ペア番号の組。生成乱数や途中状態の共有を表さない。
- `reviews/qualitative-review.json`：提出された可視文書と固定コードの読解記録。提出hash・ファイルhash・行番号を伴う。実装の内心や全経路の動作を証明するものではない。

個々のRun、条件別統計、予定ペア差、機能別集計、直接3 ID／後続10 ID／その他44 ID、応答回数の分解、終了理由、到達範囲、外れ値、順序感度分析は`data`内に分けて保存する。代替モデルがあれば主モデルの比較から分けて記述する。

bootstrapは取得バッチ内の完全な予定ペアを復元抽出する。各バッチのペア数を維持し、20,000回・seed 20260911のpercentile 95%区間を作る。欠測ペアはこの推定からだけ除き、Run別の記述データは残す。57 IDを独立な標本数として扱わない。

指標ごとの欠測により、トークン差と合格率差に使うペア数が異なる場合がある。条件別平均は値がある全Run、ペア差は両条件の値があるペアを使うため、欠測があれば二つの平均差は一致するとは限らない。保存されたID・ケース行の件数は原本の網羅性を示し、評価不能時の雛形を含む場合には業務操作を実行した回数を表さない。

## 独立保管からの復元確認

原本は`C:\Users\mwam0\ResearchArchives\sample1`の追記型パッケージで保管する。Runごとに入力、固定ソース、lockfile、実行条件と管理版、CLIログ、応答・usage・telemetry、評価原本を保存する。`source/additional/retention.json`と`private-evidence-index.json`は、そのパッケージと復元receiptへの索引である。公開用フォルダには非公開の評価コード・画面・traceを含めない。

新しいエクスポートの再現確認では、独立保管から復元した管理コードと原本を用いる。累計の再分析確認では、復元した入力・読解記録・生成コード・ライブラリ・フォントだけをDockerへ渡し、ネットワークを無効にしてCSV／JSON、SQLiteの論理内容、PNG／SVGを比較する。具体的な参照と実施結果は`checks`の検証記録で確認する。Pythonのファイルアクセス制限を使った確認と、Dockerに原本をマウントしない確認は区別して記録する。

## 将来、同じ提出物を再採点するとき

今回のレポート生成コマンドには再採点処理を含めていない。将来の再採点では、実装を再開せず、保管した提出hashが一致する作業コピーを復元する。採点する版のコード・依存lockfile・実行image・ケース定義を新たに固定し、新しい評価UUIDを割り当てる。Run UUID・提出hash・新評価UUID・採点版hashを組として保存する。

旧`evaluation-ref`、評価原本、invalid／pending、裁定は上書きしない。新評価を選ぶ場合は、選択理由・評価版・評価UUIDを明示する新しい分析版を作る。v6を使う場合の凍結hashは`a097b9baf7bfa605cb054deac151be6ade1b88bcdcb36f6fce89685e199d3cc3`。採点基準を変えた結果は今回の同一基準の比較へ混在させない。

## HTML表示と独立レビュー

```sh
node render_preview.mjs --modules /path/to/node_modules
```

Node.js、marked、Playwright、インストール済みMicrosoft Edgeを使用する。HTMLの本文はMarkdownをそのまま変換する。外部HTTPアクセスを遮断し、画像6枚の読み込み、横方向のはみ出し、本文の主要箇所を確認する。ブラウザ以外のデータ生成にはNode.jsを必要としない。

本文の考察は研究管理者による解釈であり、集計コードが自動的に正当性を保証するものではない。完成稿は執筆履歴を共有しない別エージェントがレビューし、指摘・修正・再確認を`reviews`へ記録する。同じ系列のモデルによる別コンテキストのレビューであり、人間による査読や独立した追試とは区別する。

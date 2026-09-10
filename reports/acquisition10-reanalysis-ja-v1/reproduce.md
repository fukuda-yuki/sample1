# 観測を増やさずに再生成する

このフォルダのsourceには、元SQLiteの同一コピーと固定した補助資料があります。元の5テーブルは新しいanalysis.sqliteにもそのまま残り、report_から始まるテーブルだけが今回の派生分析です。

## 数値と本文

このフォルダを作業ディレクトリとして、Pythonから次を順番に実行します。実験の管理スクリプト・gateway・アプリ・評価器は起動しません。

    python -B rebuild.py
    python -B write_report.py
    python -B build_notebook.py
    python -B render_figures.py --data analysis-results.json --output figures

必要な数値計算ライブラリはNumPy、図はMatplotlibです。使用版はanalysis-runtime.jsonとfigures/visual-verification.json・chart-map.jsonに記録しています。実際に使用したPythonはWSL Ubuntuの /home/mwam0/.venvs/sample1-acquisition10/bin/python です。

図の日本語フォントはWindowsのYu Gothic（C:/Windows/Fonts/YuGothR.ttc）、代替はMeiryoです。SVGは文字をpath化しているため、閲覧側へのフォント追加は不要です。再描画には対応フォントが必要です。

Notebookは通常のPython/SQLセルだけで構成しています。build_notebook.pyはそれらを一つの名前空間で順に実行し、stdoutを保存します。Jupyterカーネル・画面を起動したとは記録していません。Jupyterがある環境ではanalysis.ipynbを開き、このフォルダをカレントディレクトリとして全セルを実行できます。

## 入力と列の意味

- source/analysis.sqlite：元レポートのSQLiteをバイト単位でコピーした入力。
- analysis.sqlite：元5テーブルと今回のreport_派生テーブル。
- report_runs.total_tokens：全20件の元observed_tokensを確定総量として採用した値。
- source_total_tokens・source_usage_complete：旧規則による値・フラグ。上書きしない。
- report_id_results：同一Run・IDの全ケース合格で1点。T-006-05の両ケースを維持。
- report_interpretations：判断記録・固定コードの閾値と、別々の証拠への参照。
- report_trace_evidence：保存済み2ケースから選択した必要な事実とhash。
- queries.sql：名前付きSQL。tablesのCSV、analysis-results.json、本文・図の起点。
- claims.json：主張ID、SQL・数表・Run UUID・評価UUID・証拠・代替説明の対応。

分析UUIDはsource-manifest.jsonの値を再利用します。入力採用規則や分類を変える場合は、このフォルダを上書きせず、新しい分析フォルダとUUIDを作り、今回の結果を残します。新評価UUIDは発行していません。

## 原本から切り離した再生成検証

verify_delivery.pyは、新しい検証用ディレクトリへ入力と分析コードだけをコピーし、旧Run・旧レポート・非公開評価・archive・元管理コードへのPython/SQLiteアクセスを拒否したプロセスで再生成します。複製側のSQLite・本文・表・Notebook・全図とのバイト一致、および原本のSHA256不変を確認します。

    python -B verify_delivery.py

同じ分析UUIDの検証用ディレクトリが既にある場合、このコマンドは上書きを拒否します。提出時の実行結果はverification.jsonに保存済みです。データの再集計だけなら上の4コマンドで足り、原本の再読取は不要です。

evidence/collect_evidence.pyは、元資料が手元にある場合に読解証拠の出典を再確認するためのスクリプトです。再生成には実行不要です。既存出力と違う抽出結果の上書きを拒否します。保存済み評価コード・traceを読むだけで、採点を起動しません。

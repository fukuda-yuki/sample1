# v3の再生成手順

対象は固定済みの通常30件・不整合30件。モデル呼び出し、アプリ実行、再採点は行わない。旧レポートの計算結果や本文を読み込んで更新する処理もない。

## 入力と主なファイル

- `source/raw-export-a.sqlite` と `raw-export-b.sqlite` は元のRun・ケース行を保持した固定入力。計算時はUUIDで一つに結合する。ファイルを分けたのは来歴を保つためであり、条件比較の層として使わない。
- `source/observations.sqlite` は保存済みのusage内訳、固定コードの採用閾値などを持つ観測行。旧集計・旧図・旧本文は利用しない。元のケース全行との一致を `analyze.py` で確認する。
- `evidence/` は保存された原本を今回読み直した結果。`data/selected-request-trajectories.csv` は選択した3件のusageの派生行。
- `analysis-plan.json` に二群の分析単位、欠測、bootstrapの条件、探索的な分析であることを記録した。
- `source-manifest.json` は入力13ファイルと既存レポート390ファイルのSHA-256。

## 通常の数値・図表の再生成

WSL Ubuntuの既存Python環境を使用した。必要なのはPython、NumPy、Matplotlib。日本語フォントにはWindowsのYu Gothicを用いた。

以下はリポジトリのルートから実行する。出力先はこのv3フォルダだけである。

```bash
PY=/home/mwam0/.venvs/sample1-acquisition10/bin/python
R=reports/acquisition30-cumulative-ja-v3
"$PY" -B "$R/analyze.py"
"$PY" -B "$R/query_evidence.py"
"$PY" -B "$R/build_support.py"
"$PY" -B "$R/render_figures.py"
"$PY" -B "$R/verify.py"
```

`analyze.py` はコピーしたSQLiteだけを読み、60 Run・3,420 Run×ID・3,480ケースの一致、全60件のモデル、UUID、提出hash、固定v6 hashを検査する。分析DBのruns表には取得バッチ・予定ペア・実行順の分析列を作らない。来歴だけをprovenance表へ保持する。

bootstrapは条件ごとに異なる乱数インデックスを引く。トークンは各30件、得点は観測値のある28件・29件を同じ大きさで復元抽出し、20,000回の差から2.5・97.5%点を求める。57評価IDを独立標本として抽出する処理はない。

3件の合格率欠測はSQLiteのNULLおよびJSONのnullとして残る。CSVでは空欄である。原出力の点数はsource_passed_idsに保持する。completedで0点だったRunの分析値は0のまま残す。

## HTML

同じMarkdown本文をmarkedで変換し、ローカルのChromiumで画像・表・横はみ出しを確認する。Node依存はCodexの既存runtimeを使用した。PowerShellから次を実行する。

```powershell
& 'C:\Users\mwam0\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' `
  'reports/acquisition30-cumulative-ja-v3/render_preview.mjs' `
  --modules 'C:\Users\mwam0\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
```

## 原本との再照合と、別場所からの再生成

`audit_saved_sources.py` は引用元の固定コード・判断記録139ファイル、`capture_saved_evidence.py` はCSVの保存記録57件と3 Runのusage原本を読み直す。通常の再集計には不要であり、非公開原本へのアクセスがある管理環境だけで使う。いずれも読み取り専用で、評価器は実行しない。

`verify.py --check-originals` は、元レポート群と入力のhash不変を確認する。`replay.py` はv3の入力とスクリプトを新しいパッケージとして既定の独立保管庫へ保存し、新規フォルダへ復元する。復元入力と保存済みPython runtimeだけを、ネットワークを遮断したDockerへマウントする。元のリポジトリ・保管庫・非公開評価場所がコンテナ内にないことを確認してから、再計算・SQL・図表生成を行う。33成果物のbyte一致（SQLiteは論理内容）を比較し、元の公開出力を上書きしない。実行結果と保管参照は `checks/replay.json` に保存する。

本文は人が読める主張・根拠・代替説明を含む手書きの分析文章であり、計算スクリプトが自動的に解釈を決めるわけではない。数値はSQLと検証コードで追跡でき、完成稿のレビューと対応はreviewsフォルダに保持する。

将来v6とは別の評価を行う場合は、原提出hashを保持したまま新しい評価UUIDと評価版を付ける。本稿はその実行を指示せず、既存得点やinvalid/pendingを上書きしない。

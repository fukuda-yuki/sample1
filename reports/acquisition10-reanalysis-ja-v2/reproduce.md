# 再生成とファイルの読み方

主文書は[report.md](report.md)。図はfigures、Run別・項目別データはdata、入力の固定コピーはsourceにある。本文の解釈は著者が記述した文章であり、集計スクリプトが自動的に研究上の正しさを判定するものではない。

## 数値と6図を再生成する

Python 3.12、NumPy、Matplotlibと日本語フォントYu Gothicを使用する。今回の環境では、WSL Ubuntuの `/home/mwam0/.venvs/sample1-acquisition10/bin/python` と `/mnt/c/Windows/Fonts/YuGothR.ttc` を利用した。実測したライブラリ版は[data/runtime.json](data/runtime.json)と[図のmanifest](figures/figure-manifest.json)にある。

このフォルダをカレントディレクトリとして実行する。

```sh
python -B analyze.py
python -B render_figures.py
```

別の出力先へ再生成する場合：

```sh
python -B analyze.py --output /path/to/replay/data
python -B render_figures.py --data /path/to/replay/data/results.json --output /path/to/replay/figures
```

analyze.pyは、このフォルダのsource-manifestに登録された12入力のhashを照合し、コピーしたSQLiteを読み取り専用で開く。元の実装、評価器、gateway、モデルAPIを起動しない。新しいSQLiteは作らず、CSV・JSONを出力する。render_figures.pyは派生JSONからPNG・SVGを描く。

## 列と分母

- `recorded_total_tokens`：元`observed_tokens`の全20件を採用。未記録分は補完しない。
- `source_total_tokens` / `source_usage_complete`：元の値・完全性フラグを保持。nullを0に変換しない。
- `passed_ids` / `recorded_pass_rate`：保存済み合格ID数と、57を固定分母とした割合。
- `evaluation_validity`：旧invalid/pendingの裁定。今回の分析で更新しない。
- `pair_id`：元の予定順ブロック。モデル乱数や生成状態の共有を示さない。
- `source/qualitative.json`等：v1が作成した保存資料の読解索引をそのまま保持。新たな実行観測ではない。

## 検証

```sh
python -B verify.py
```

入力と生成コードを新しい検証ディレクトリへコピーし、そのコピーから表図を再生成する。dataとfiguresの生成物を比較し、本文の主要数値・表・画像参照も検査する。元レポート118ファイル、今回利用した入力、全20配布契約のhashを照合する。これはコピーした入力による再現確認で、OSレベルの隔離試験ではない。

検証出力はchecks以下に保持する。書き換えた入力へ旧receiptを流用しない。解析定義・入力を変更するときは、このv2を保持したうえで新しい分析版を作る。

## 表示とレビュー

report.mdが正本であり、report-preview.htmlは同じMarkdownをブラウザで読めるようにした補助表示である。`render_preview.mjs` はNode.js、marked、Playwrightとインストール済みMicrosoft Edgeを使い、外部ページへ接続せずローカルファイルを描画する。依存ライブラリの場所は実行時の`--modules`で指定できる。別のブラウザは`--channel chrome`等で指定する。

```sh
node render_preview.mjs --modules /path/to/node_modules
```

画像の読み込み・画面幅・表示画像の確認はchecksの記録、独立エージェントの読解はreviewsの記録で区別する。図表データ、再生成コード、本文、完成稿レビューの各出典とhashを残す。リモート公開、Issue更新、新規実装Run、再採点は今回の作業範囲に含めない。

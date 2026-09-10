# 検証記録の読み方

研究アプリの合格数と、このフォルダの管理・再現性の検証は異なる。fixtureの成功を実モデルの成功件数へ加算しない。v6の製品品質の裁定は元のinvalid/pendingを保持する。

| 証拠 | 確認対象 |
| --- | --- |
| `preflight/manifest.json` | 開始前の並列制御8テスト、関連回帰33テスト、gateway、receipt、生成専用ゲート、実Dockerのnative CLI 5件＋評価代替処理などの保存証拠。テスト群は範囲が重なるので件数を合計しない。 |
| `docker-drills/manifest.json` | 合成HTTP providerによる逆順完了、503同時代替予約、429、保管障害、停止・再開、評価出力作成後の登録再開。初期fixtureの失敗も理由を残す。実モデル呼び出し0、非公開v6の業務assertion実行0。 |
| `analysis-missing-fixture.json` | 未開始と起動不能の原0/blocked出力を、分析で欠測として扱う検証。前回の保存値も照合。 |
| `acquisition-audit.json` | 実40件の停止、提出固定、入力・版・UUID・hash、子エージェント禁止、原本・関連記録・評価パッケージと復元物の全件一致、旧320ファイル不変。 |
| `raw-restored-replay.json` | 追加40件の原本を復元し、元の評価場所へアクセスできないDockerからエクスポート。CSV・JSONL・provenanceとSQLiteの論理内容を比較。 |
| `cumulative-restored-replay-*.json` | 復元した入力・読解記録・計算コード・ライブラリ・フォントだけで累計分析を再生成。ネットワークなし。CSV/JSON/PNG/SVGと補足本文はbyte一致、SQLiteは論理内容一致を確認。 |
| `replay-output-bindings.json` | 完了した復元出力と提出データをもう一度比較し、現在の出力hashへ結び付ける。SQLiteは全テーブルの行から求める論理内容のhashを使う。 |
| `verification.json` | 60枠、3,420 ID・3,480ケース、SQL結果、20主張、40件の静的引用・7件の観測証拠、旧hashを照合。 |
| `browser-render.json`・`screenshots/` | Markdownから生成したHTMLの6画像表示、1100px/800px幅の横はみ出し、本文・表・図の実表示。研究アプリの再実行ではない。 |
| `secret-scan.json` | 実gateway鍵そのものが公開対象・新規Run原本・保管パッケージに含まれないことを走査。値やhashは出力しない。 |
| `publication-secret-scan.json` | 本文の受入結果・リンクを更新した後、公開ファイルの集合をもう一度検査。大きな原本の全走査と分けて記録。 |
| `final-acceptance.json` | 上記と独立レビューの最終結果を、提出する本文・HTML・データのhashへ結び付けた受入記録。リモート発行はIssue #49の別記録。 |

原本復元の検証スクリプトは`../archive_and_replay.py raw`と`../archive_and_replay.py report`。この二つは本研究の既定保管庫へ追記型パッケージと新しい復元先を作る。保存済みデータから通常の数値と図だけを再生成する手順は[再現手順](../reproduce.md)を参照。

# normal/anti各10開始のデータ取得

2026-09-10のユーザー承認に基づく新規バッチ。過去のpilot・受入Runは標本に含めない。

- 各条件10開始、合計20開始。Muse Spark 1.2 Contributor、各3600秒、effort未指定、実装子agentなし。
- seed=20260910のペア内無作為順を開始前に固定。K=1、dispatch limit=1。Run停止・固定・保全・復元・usage/monitor照合後だけ次を開始する。
- 上流503時だけ同条件の次枠で1.3 Contributor→Omen Alpha→MiMo-V2.5へ進む。成功後は1.2へ戻す。代替も枠を消費し、異モデルは別集計。429、回収・計測障害、代替全滅は停止する。
- HTTP503応答自体のusage未提供と、成功応答の計測欠損を区別する。全リクエストの終端と成功応答のnative照合が成立し、503拒否だけが欠測である場合は承認済み代替を許可する。その場合も総量null、usage_complete=falseと観測下限は維持する。
- 各実装は新規・隔離環境で自条件specとRUN_CONTRACTだけを受け取る。AP-001は変更しない。

## 開始条件と操作

`data-acquisition`は生成専用の明示的な実行phase。旧pilotやmeaningful-evaluationの未完了ゲートを成功扱いにしない。生成設定、入力、予定順、管理コードと生成用証拠をhashで固定し、独立保管先から復元したgeneration-readinessを確認する。採点完了を生成開始条件に含めない。

正規の実行入口は`serial_acquisition.py`。既存`copilot_parallel.dispatch`をK=1/limit=1で繰り返す。既存slot・UUID・予約の再利用による新規実装は禁止。再開前には元の制御プロセス停止と回収状態を確認する。失敗したUUIDを未開始へ戻さない。

```sh
python scripts/serial_acquisition.py <batch> --locator <monitor-locator.json> --secret-file <gateway-only-key> --execute-real-model
python scripts/copilot_batch.py status <batch>
python scripts/copilot_batch.py recover <batch> --locator <monitor-locator.json>
```

鍵はWindowsユーザー環境変数`OPENCODE_GO_API_KEY`から取得し、アクセス制限した一時秘密ファイルをgatewayのみへmountする。鍵をargv・worker環境・成果物・Issue・ログへ書かない。保管・公開時には鍵との一致と秘密情報候補を検査する。

## 評価と再採点

20開始終了後、または停止条件成立後に、固定v6 `a097b9baf7bfa605cb054deac151be6ade1b88bcdcb36f6fce89685e199d3cc3`で回収済み提出物を初回1回ずつ独立評価する。低得点・未完了・時間切れを除外しない。採点は生成物へフィードバックしない。

```sh
python scripts/copilot_batch.py evaluate <batch> --pending --private-root <private-v6> --evaluator-image <pinned-image> --validity <validity.json>
python scripts/copilot_batch.py export <batch> --validity <validity.json>
python scripts/check_copilot_analysis_restore.py <parent-of-batch> <new-restore-output> --archive <archive> --validity <validity.json>
```

rawと妥当性裁定を分け、v6既知制約・前提波及・未到達を記録する。57 ID・58ケース・等配点を維持し、評価不能を0点としない。将来の評価版は旧結果を残して別選択を作り、同一提出hashを新しい評価UUIDで採点する。再採点のための実装改変は行わない。

## 保存・提出

固定ソース、配布物、設定・管理コード・実行ログ、raw usage、telemetry、評価原本・画面・traceを研究者用保管庫`C:\Users\mwam0\ResearchArchives\sample1`へ保存する。runtime imageと依存キャッシュの既存不変パッケージをhashで参照し、今回の管理コード・評価器ソースは別に保存する。

公開物は日本語Markdownレポート、Run別CSV/JSON、分析SQLite、モデル別散布図と再現手順。リモートブランチへ発行可能。私的評価コード・ケース・画面・trace・鍵は公開しない。実行進捗・受入証拠の正本はGitHub Issueとする。

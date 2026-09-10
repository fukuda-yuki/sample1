# 追加40開始と累計60件の報告

2026-09-11のユーザー承認。`parallel-preserve-first-v1`は、既存の直列取得ゲートを変更せずに適用する新規取得ポリシー。

- normal/anti各20開始、合計40開始、最大5枠。保存・復元まで占有し、空き枠を固定予定順に補充する。seed 20260911。
- Muse Spark 1.2 Contributor、Copilot CLI 1.0.83-5、前回と同じimage、60分、effort未指定、実装内子agentなし。
- 上流503のみ同条件の次の未開始枠で1.3 Contributor、Omen Alpha、MiMo-V2.5。各失敗Runから次候補への要求を回収順FIFOで一度だけ予約し、別の通常枠は1.2。全て40枠に含める。
- 継続的429（同一Runで2回以上）、代替503全滅、停止・保全・復元未確認は新規開始停止。進行中Runは回収する。再開は所有プロセス終了、既存原本照合、停止理由の解決記録を伴う。開始済み枠は再利用しない。
- 原本確保後のusage欠測、monitor障害、評価invalid/pending、低得点は取得停止理由にしない。
- 取得中の評価は最大1、全実装終了後は最大4。原本と評価のUUID/hashを照合し、共有台帳更新とmonitor取込は単一管理経路に限定する。
- AP-001、既存v6のhash、57 ID/58ケース・等配点を固定。業務資料は自条件specのみ。新旧成果物を修正・取り直ししない。
- 鍵はOPENCODE_GO_API_KEYからgateway専用一時ファイルへ渡し、worker、ログ、Git、保管原本へ含めない。

正規入口は `scripts/parallel_acquisition.py`。新しいexperiment、authorization、generation-readinessの保管・復元を開始前に要求する。旧20件のゲートや裁定を新たな取得許可へ読み替えない。

累計は前回v2に含まれる20件と今回40枠だけ。指標は記録済み総トークンと保存済みv6の合格率で、有効品質とは分ける。バッチ・モデル・欠測を明示し、分析方針を開始前に固定する。進捗・実測証拠の正本は今回用GitHub Issue。

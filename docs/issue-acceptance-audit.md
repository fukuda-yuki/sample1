# Issue 受入条件の監査

監査時点: 2026-09-05 23:19 JST（14:19 UTC）。GitHub #1〜#11 の最新本文・コメントを `gh issue view` で読み、ローカル成果物と実行記録に照合した。全 Issue は OPEN。以下の「達成」はローカルの当該受入範囲を指し、Issue の完了操作やリモート反映を意味しない。実験の管理基盤が動くことと、比較実測が完了することを分けて判定した。

| Issue | 判定 | 確認できた根拠 | 残り・制約 |
|---|---|---|---|
| [#1 全体](https://github.com/fukuda-yuki/sample1/issues/1) | 未完了 | 下記の仕様整理・隔離・停止固定・計測・集計基盤、および normal の実装 Run 完了。 | 両 pilot の有効な独立採点・最初の実測図・比較反復・観測に基づく判断が必要。 |
| [#2 実験設計](https://github.com/fukuda-yuki/sample1/issues/2) | 文書要件は達成 | [experiment-design.md](experiment-design.md)、[decision-log.md](decision-log.md) に対象、意図した AP-001、固定条件、評価単位、ユーザー確定値、非対象を記録。 | 実測の完了証拠にはならない。変更時は版と理由を追記する。 |
| [#4 共通実装指示](https://github.com/fukuda-yuki/sample1/issues/4) | 達成 | [implementation_prompt.md](../implementation_prompt.md) は配布する spec と共通契約で完結。条件名・非公開採点情報を実装入力へ要求せず、共通の起動・初期化・外部出力契約を定義。 | 公開契約を変更する場合は既存 Run と同じ入力として扱えない。 |
| [#3 役割分離](https://github.com/fukuda-yuki/sample1/issues/3) | 達成 | [agent-roles.md](agent-roles.md) と [AGENTS.md](../AGENTS.md) に研究管理・実装・評価の権限、情報境界、判断例を記録。人格や自己申告を品質として採点しない。 | 実運用でも失敗ケースを実装側へ返さないことを継続する。 |
| [#5 要件監査](https://github.com/fukuda-yuki/sample1/issues/5) | 台帳・文書は達成 | [requirements-audit.md](requirements-audit.md)、[57 ID 台帳](../evaluation/requirements-ledger.json)、[test_items.md](../test_items.md)、[antipattern_list.md](../antipattern_list.md)。未提示期待値を緩和し、公開契約追加と区別。検証器で件数・重複・連番・AP 差分を検証。 | 台帳との対応だけでは採点 helper の正しさは保証しない。実判定の再確認は #7。 |
| [#6 入力・実行隔離](https://github.com/fukuda-yuki/sample1/issues/6) | 基盤と隔離検証は達成 | [workspace-isolation.md](workspace-isolation.md)、[gateway-isolation-integration.json](gateway-isolation-integration.json)、[run-separation-integration.json](run-separation-integration.json)。許可リスト配布、ホスト canary・外部 GitHub・任意 gateway 経路の拒否、同ポートの 2 Run 分離を実環境で確認。 | 外部の private evaluator と実行環境は Git の公開ツリーだけでは再現できない。 |
| [#7 非公開 E2E](https://github.com/fukuda-yuki/sample1/issues/7) | 実装・旧版校正済み／最終判定保留 | [evaluator-version.json](../evaluation/evaluator-version.json)、[calibration-summary.json](../evaluation/calibration-summary.json) に正常・別 UI の 57/57、閾値・表示・通知・権限の変異検出、起動不能と評価器障害の区別を保存。各実行にコード・依存・台帳の snapshot を保存。 | 実 normal の採点で helper 不具合が判明し、その採点は無効。修正版の校正と同じ固定提出物の再採点が必要。旧版 fixture の合格だけで完了としない。 |
| [#8 Run 管理](https://github.com/fukuda-yuki/sample1/issues/8) | 基盤は達成 | [run-protocol.md](run-protocol.md)、[protocol-integration.json](protocol-integration.json) に通常・異常・上限終了、子孫停止、提出物固定。normal 実 Run でも `agent_completed`・`processes_stopped=true`・`submission_fixed=true` を確認。 | anti は実行中。全予定 Run の実施は #11。制御処理 timeout と実装予算終了を区別する修正は次 Run から適用。 |
| [#9 総トークン計測](https://github.com/fukuda-yuki/sample1/issues/9) | 計測基盤と normal 実測照合は達成 | [token-accounting.md](token-accounting.md)、[measurement-control-change.json](measurement-control-change.json)。normal は 75 リクエスト、5,798,122 tokens、CLI 原本と一致、`usage_complete=true`。重複・累積・欠測・中断保存をテスト。 | anti の確定総量は未取得。現 Run の原本保全と次 Run 適用を区別し、管理スクリプトの新旧 hash を記録。欠測を 0 にしない。 |
| [#10 集計・描画](https://github.com/fukuda-yuki/sample1/issues/10) | 基盤検証済み／実測図は未完了 | [metrics.md](metrics.md)、[analysis-integration.json](analysis-integration.json)、[analysis](../analysis/) に固定分母・58 必須ケース整合・版混合拒否・欠測保持を実装。実際の校正結果 JSON と合成 manifest の接続、合成図を検証。 | 合成図と校正品質を実装モデルの比較結果として扱わない。有効な pilot 採点を接続した図と欠測表の作成・目視確認が必要。 |
| [#11 Pilot・初期反復](https://github.com/fukuda-yuki/sample1/issues/11) | 未完了 | [pilot-plan.md](pilot-plan.md)、[execution-order.json](../config/execution-order.json)、[version-manifest.json](../config/version-manifest.json) に phase・固定順序・版・変更規則を記録。pilot normal は固定済み、anti は実行中。 | 両条件の端から端までの検証、失敗・上限・欠測を含む最初の図、同じ版の comparison 各 3 Run、観測に基づく継続判断が残る。無差・逆方向もそのまま報告し、この 1 アプリ・AP-001・当該構成に結論を限定する。 |

## 実測と公開状態の注意

normal の Run ID は `250df4e7-f8f9-44cd-8324-db24e050962f`、anti は `e849b8d9-60e2-464f-bea9-11d24134674f`。実行記録は `results/runs/pilot-1-normal/` と `results/runs/pilot-1-anti/` にある。normal の実装完了は要件充足を意味しない。採点 helper 不具合による無効結果を実装失敗や確定した品質値として引用しない。comparison は監査時点で未実施であり、効果の方向・大きさは未確認。

[最新の親 Issue コメント](https://github.com/fukuda-yuki/sample1/issues/1#issuecomment-5552357663) に進行状況と Push 制約を記録済み。監査時点のローカル HEAD は `609a293`、`git ls-remote` で確認した `origin/codex/issue-1-experiment` は `94c9502b904afa0371f8ffb562b08984c799515e`。Push は自動承認レビューで拒否されており、`609a293` 以降の変更はリモート未反映。したがって、ローカル基盤の達成を GitHub 側の成果物反映・Issue 完了と同一視しない。この監査では Issue 更新・close・commit・push を行っていない。

## 2026-09-05 23:43 JST の追記

両 pilot は実装終了・プロセス停止・提出物固定済み。normal 5,798,122、anti 4,754,779 tokens を native input+output と照合し、一致・欠測なしを確認した（[照合記録](pilot-usage-reconciliation.json)）。#8/#9 の pilot 実測は両条件で得られた。

起動 helper 修正後の採点で未提示 UI 制約による誤判定を確認したため、両採点を無効として停止・保全した（[障害記録](pilot-ui-contract-incident.json)）。#7/#10/#11 の有効採点・実測図・比較反復は未完了である。独立した UI 変種 fixture で校正を追加し、修正後の同じ版で両固定提出物を再評価する。[Issue #11 更新](https://github.com/fukuda-yuki/sample1/issues/11#issuecomment-5552503871)に原本・版・未達事項を記録した。

## 2026-09-06 停止時点の追記

[パイロット結果](pilot-results.md)のとおり、校正は完了したが、再採点で自己登録経路を扱えない追加問題が確認された。ユーザーの停止条件に従い品質未確定で停止。#5は公開F001の自己登録許容と研究者用管理者前提の追加監査が残り、#7は評価器修正・追加校正・同じ提出物の再採点が残る。#10は欠測表・図まで作成済みだが有効品質での更新が残る。#11は両実装/使用量完了・有効品質未確定、比較6 Runは開始しない。#1は全体完了として閉じない。現在の正式なIssue状態と再開地点はGitHub #1/#11の停止記録を参照する。

# 仕様書内不整合と実装Runの探索実験

[新規pilot-2の停止結果](docs/pilot-2-results.md)：normalは管理環境障害でモデル呼出し前に失敗、anti未開始。失敗Runの原本・停止記録を独立保管・復元済み。追加Runは禁止。
[2026-09-06 パイロット結果と停止地点](docs/pilot-results.md)：旧2 Runは原本欠落で評価不能、品質nullと過去の使用量照合記録を保持。[原本保全・復元](docs/preservation.md)の合格を条件に、新規pilot-2を各条件1回だけ実施して停止する。追加比較は許可しない。実測と現在状態の正本はGitHub #1・#11。

このリポジトリは申請管理アプリを製品として開発する場所ではなく、仕様書内の不整合が実装Runの総トークンと非公開E2Eへの適合度にどう関係するかを調べる研究管理用リポジトリです。作業の正本は [Issue #1](https://github.com/fukuda-yuki/sample1/issues/1) とその子Issueです。

題材は20機能の申請管理システムです。normalとantiの差はAP-001（共通ルールとF-006の承認閾値の不整合）。無関係な長文やノイズ一般の実験とは区別します。差なし、品質向上、トークン増加も観測結果であり、悪影響を出すことを成功条件にしません。

- [研究設計・情報境界](docs/experiment-design.md)
- [環境復元から実行・採点・集計までの手順](docs/reproduce.md)
- [研究支援役と作業手順](docs/agent-roles.md)
- [判断履歴](docs/decision-log.md)
- 公開入力: [共通実装指示](implementation_prompt.md)、条件別の [normal](normal/spec.md) / [anti](anti/spec.md)
- [公開要件監査](docs/requirements-audit.md)、[実行隔離](docs/workspace-isolation.md)、[Run手順](docs/run-protocol.md)
- [評価器](docs/evaluator.md)、[総トークン計測](docs/token-accounting.md)、[集計定義](docs/metrics.md)、[パイロット手順](docs/pilot-plan.md)

研究管理README、AGENTS、他条件の仕様、注入一覧、テスト項目書は実装ワークスペースへ配布しません。実装役にはその条件の `spec.md` と共通実装指示だけを渡します。非公開評価コードはこのGitリポジトリの外に保管します。

文書・スクリプトの存在と実験の実施・検証済みは別です。実行記録のある結果だけを完了根拠とし、未実施・環境障害・欠測は隠しません。

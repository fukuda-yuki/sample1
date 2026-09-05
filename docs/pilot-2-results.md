# 新規パイロットの結果と停止地点（pilot-preservation-002）

**新規パイロットは正常完遂していない。normalの開始試行がモデル呼出し前の管理環境障害で失敗し、antiを開始せず停止した。失敗Runの原本と停止記録は独立保管・復元済み。**

| 予定 | Run ID | 結果 | 総トークン | 有効品質 |
|---|---|---|---|---|
| pilot-2-normal | b6b16b13-af18-4243-b38c-764481115357 | gateway準備失敗、モデル・worker未開始 | null（欠測） | null（未採点） |
| pilot-2-anti | 未発行 | 先行Run失敗により未開始 | 対象なし | 対象なし |

モデルgatewayの開始・完了usageイベントはいずれも0件。Dockerのgateway開始失敗記録からモデル呼出し前の障害と確認したが、不完全usageを総量0の座標へ変換しない。manifestのelapsed_secondsは失敗後の固定処理だけを測った値であり、実装時間やgateway準備全体の所要時間ではない。

## 原因と修正

直接原因は、既存Dockerのbridgeが指すdocker0インターフェースの欠落。Docker journalにはgatewayのnetwork endpoint作成時の `Device does not exist` が残る。

今回、私が復元試験用に起動した別daemonは、データ領域・containerd・socketを分離していたが、ホストのネットワーク空間を共有していた。同じ起動方式（--bridge=none）が既存docker0を削除することを、隔離namespaceのmarker bridgeで再現した。この管理操作によるネットワーク干渉が今回の原因と判断する。被評価実装の失敗ではない。旧2 Runの原本欠落原因は、これとは別に未確定のまま。

既存bridge設定に合わせdocker0（172.17.0.1/16）を復旧し、認証なしのTCP接続確認に成功した。モデルリクエストは送っていない。今後の復元試験は `unshare --net` 内で両daemonを起動する。標準の起動経路はscripts/launch_restore_drill.py。ホストnamespaceでの検証を拒否するガードと、gateway失敗段階・stderrを将来のmanifestへ残す処理を追加した。既存Run原本は書き換えていない。

## 保全と成果物

保管先は `C:\Users\mwam0\ResearchArchives\sample1`。

- Run原本: `run-b6b16b13-af18-4243-b38c-764481115357`
- 停止原本: `stop-b6b16b13-af18-4243-b38c-764481115357`
- 原本・復元receipt・原因の詳細: [pilot-2-stop.json](pilot-2-stop.json)
- 表: [runs.csv](pilot-2-artifacts/runs.csv)、予定状態: [planned-status.json](pilot-2-artifacts/planned-status.json)
- 図: [tokens-quality.png](pilot-2-artifacts/tokens-quality.png)、[欠測表](pilot-2-artifacts/tokens-quality.missing-runs.csv)

worker未生成のためnative-usage.jsonは未生成であり、パッケージのmissing一覧に保持した。後から捏造しない。評価も実施していないため、公開表では集計器の仮のケース件数を空欄とした。品質nullを0点や57機能の実装失敗に読み替えない。

旧Run・合成校正と新Runを混合していない。図は全1 Run・座標欠測1として点を描かず、antiは未開始予定として表に残す。今回からAP-001の効果や条件の優劣を結論づけない。

## 現在の停止と残作業

allowed_startsは空。normalの予約は消さず、anti・旧Run再実装・比較6 Run・自動取り直しを開始しない。全起動経路の拒否を[停止検証](pilot-2-stop-guard-verification.json)で確認した。

有料モデルを使わない修正版の復元試験結果は別ファイルへ記録する。成功しても新規実装Runの許可を復活させない。正常に測定できる新しいパイロットの取得は未完了であり、再開には新しいRun IDと実行範囲のユーザー判断が必要。研究全体とIssue #1/#11は完了として閉じない。

### 修正版の復元検証結果

[ネットワーク分離後の復元検証](preservation-restore-isolated-verification.json)は合格。空のDocker/containerdへimage実体を読み込み、通常終了・打切り・異常終了、合成usage再集計、両登録経路の正常57/57と閾値変異各13失敗、採点結果の保存・復元を確認した。ホストbridgeのifindex・MAC・IP情報は前後一致し、終了後の認証なしTCP通信も成功した。実装Runの許可は復活させていない。

コード検証は[32件の保全・実行系、25件の分析、57 ID/AP-001検査](preservation-final-code-verification.json)。成功した校正・保全検証と、新規パイロットが未完遂であることを区別する。

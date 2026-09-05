# 原本保全と復元

研究者専用の独立保管先は `C:\Users\mwam0\ResearchArchives\sample1`（WSLでは `/mnt/c/Users/mwam0/ResearchArchives/sample1`）。作業フォルダやWSLの初期化から分離する。同じ物理ドライブの故障への保証はない。実装workerへmountせず、公開Gitへ非公開評価器・原本をPushしない。

## パッケージ

`scripts/preserve.py pack <archive> <spec.json>` は明示したsourcesだけを取り込み、`packages/<package_id>/payload` と全ファイルSHA-256/サイズを含むpackage.jsonを作る。specはpackage_id、sources（保存相対名→現物パス）、metadata、references（package_id/sha256）を持つ。予約を排他的に作成し、一時パッケージを照合後に確定する。失敗したIDを再利用しない。参照する共通パッケージも実体まで検査する。

`restore <archive> <reference.json> --destination <新規領域>` はパッケージを検査して新しい場所へ復元し、再照合後にarchive/receiptsへ追記する。index改変、余分・欠落・改変ファイル、リンク、危険な相対パス、上書きは拒否する。認証や生の思考ログを取り込むために作業フォルダ全体を指定しない。

Run原本はfrozen、snapshot、manifest、実入力、usage原本と完全性、管理コード。採点原本は別パッケージでRun原本へ関連付け、結果・summary・trace・有効性台帳・判定履歴を保存する。共通パッケージは固定評価器、fixture、依存実体・lock、管理コード、入力、imageのtar実体を持つ。ハッシュのみの参照は認めない。欠測はmetadata.missingとして残し、完全な原本と扱わない。

## 開始と終了

execution-scope.jsonは新予定表と個別許可、固定共通パッケージ、復元試験の証拠を指定する。復元試験未実施・版不一致・先行Run未完了・予約済みは開始不可。予約はarchive/startsに残り、別出力先に変えても同じ予定を再実行できない。失敗は新規Runの自動再試行理由にしない。

run_codexの終了処理はgateway停止→usage確定・native照合→Runパッケージ作成→独立領域への復元照合まで実行する。submission_fixedとは別にpreservation.jsonへ保管・復元の証拠を記録する。失敗はpreservation-failure.jsonに残し、予約と部分パッケージも保持する。採点には復元したRunを使用し、採点原本の復元と有効性確認を終えてarchive/completedへ追記するまで次を開始しない。

## 有料モデルなしの復元試験

prepare_preservation.pyで旧残存資料とimage実体を保全し、seal_common.pyで固定版を保存する。check_preservation_restore.pyは空の専用Docker/containerdのデータ領域と専用socketを使用する。既存daemonやキャッシュを削除しない。保管先から全依存を復元し、imageをloadする。

固定した合成shell（network=none、認証なし）で通常終了・時間切れ・異常終了を確認する。合成usageは実測と区別し、打切り・異常の欠測理由も復元する。校正コンテナには復元済み評価器・fixture・依存だけをmountし、元の作業コピーやDocker socketを渡さない。両登録経路の正常解受入と閾値変異検出、採点原本の再復元まで成功した証拠を開始ゲートに登録する。

旧Runはdocs/original-loss-incident.jsonのとおり原本欠落で評価不能。保全したworkingは調査用であり提出物ではない。過去の使用量と新Runの品質を同じ点にしない。現在の実施状態と再開判断はGitHub #1/#11を参照する。

## 復元daemonのネットワーク隔離（2026-09-06修正）

別data-root/socket/containerdだけではホストのネットワークを隔離できない。最初の復元試験daemonがdocker0へ干渉し、新規normalのgateway起動を失敗させた。同方式のmarker削除を隔離namespaceで再現した。旧Runの原本欠落とは別の管理障害である。

フル復元試験は必ず、Dockerホスト上でrootによる `unshare --net python3 scripts/launch_restore_drill.py <研究者Linuxユーザー> <archive> <common-reference.json> <新規復元先>` から行う。launcherはホストnamespaceでは起動を拒否し、隔離namespace内で両daemonを立ち上げ、研究者ユーザーへ権限を下げてdrillを実行する。DRILLのnamespaceとホストnamespaceを証拠に残す。既存Docker/ネットワークの一括停止・初期化はしない。試験前後にホストbridgeの同一性と通信を確認する。

最初の保全・復元試験結果は履歴として残すが、追加開始許可には使わない。現行allowed_startsは空。失敗Run・原本・保全receiptは消さず、修正版試験が成功しても実装を自動で取り直さない。詳細は[pilot-2結果](pilot-2-results.md)。

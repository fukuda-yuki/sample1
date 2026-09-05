# Run終了と提出固定

`python scripts/run_experiment.py <配布先> <設定JSON> <新規Run保存先>`。
同一保存先の上書きを禁止する。設定は experiment_version、model_id、effort、agent_version、
tool_versions、subagent_policy、environment.image（digest固定）、execution_order、
command（argv配列）、budget が必須。budget は
`{"kind":"wall_clock_seconds","value":3600,"scope":"container"}` の形式。
モデル/effort/予算は研究者が決めた同一設定を条件間で使う。runnerはモデルを暗黙選択しない。

設定、入力ハッシュ、開始時刻、UUIDをmanifest.jsonに記録してから起動する。
終了コード0は agent_completed、それ以外は agent_error、時間切れは budget_exhausted、
Ctrl-Cは operator_aborted、環境障害は environment_failure。
agent_completedは受入合格を意味せず、固定提出後にだけ独立評価する。
時間上限はコンテナ作成開始から測定する。停止確認と回収には追加時間があり、elapsed_secondsに記録する。

Dockerコンテナ全体をkillしてRunning=falseを確認後、Git未追跡を含むソースをfrozenへコピーする。
node_modules/bin/obj/.git/.codex/.cache/maildropとDBファイルを除外し、manifestに除外規則を記録する。
これらの予約ディレクトリへ手書きソースを置かない。依存はlockfileから復元する。
採点はfrozenを変更せず別の評価コピーに公開手順で新規DBを作る。
残るソースのsymlink/junctionを拒否し、SHA-256をsnapshot.jsonへ保存する。
停止不能または回収不能ならsubmission_fixed=falseとし評価しない。
Docker作成前の失敗でも入力だけの提出物とmanifestを残す。未完成を集計から隠さない。

採点器は `run_experiment.verify_snapshot(frozen, snapshot)` を前後に実行し、
evaluation_id、元run_id、snapshotのハッシュを記録する。再評価は同じfrozenから新しいevaluation_id。
再実装は新しい保存先・run_idにして設定のrerun_ofで元run_idを参照する。
非公開ケースや採点結果を実装中に戻さず、片条件だけの追加指示も禁止する。

`check_container_protocol.py` はWSL Dockerで正常/timeout/エラーと子プロセス停止を実測済み。
証拠は `protocol-integration.json`。標準ライブラリテストの環境障害経路はmockを使用する。

AI実行はLinux/WSLから `python3 scripts/run_codex.py <配布先> <設定JSON> <新規保存先>
--auth <既存Codex auth.json>` を使う。wrapperが共通Codex起動argvを固定する。
gateway自身は専用内部networkと外部bridgeへ接続し、workerは内部networkだけに接続する。
gatewayへ任意URLを渡せず、外部モデルツールもgatewayで拒否する。認証はworkerへ渡らない。
実行後gateway・networkを当該Runの名前で削除し、他コンテナへ触れない。

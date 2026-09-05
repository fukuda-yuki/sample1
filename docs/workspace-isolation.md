# 配布と隔離

`python scripts/prepare_workspace.py normal <新規配布先>` と anti 版で配布する。
管理用 distribution.json は workspace の外に保存し、条件名・入力ハッシュ・バイト長を持つ。
配布許可リストは spec.md と共通の RUN_CONTRACT.md のみ。Git履歴、採点器、管理指示、過去Runは含めない。
両仕様のdiffはF-006の承認者の上下限2行のみを許可する。冒頭の100万円基準はantiでも維持する。

配布フォルダだけでは隔離にならない。基礎runnerは digest 固定の準備済みDocker image、
network none、共有HOMEなし、共有ポートなし、workspaceのみmount、read-only root、
capabilities削除で実行する。依存はimageに事前投入する。Docker socket、ホストHOME、元repoをmountしない。
新規セッションだけを使用し、コンテナ全体を終了後に削除する。

この基礎runnerでは外部モデル通信も不可能である。AI実Runは `run_codex.py` の専用internal networkと
`model_gateway.py` の固定Responses upstreamを使用する。認証ファイルはgatewayのみが持つ。
gatewayはモデルID/effortを検証し、Web検索/MCP等のremote toolsと外部image/file URLを拒否する。
workerのHOMEは空で、外部検索と子agentを無効化したCodex CLIだけを実行する。
単にnetwork有効にすることを隔離の代替としない。次のアクセス境界は実験環境の事前校正対象である。
現在のrunnerが全項目のカナリア試験を各実装Run内で繰り返す、という意味ではない。

- 対条件、管理AGENTS、採点器、過去Runのhostカナリアが読めない。
- GitHub/公開repo、任意外部URL、ホストサービス、別Runへ接続できない。
- モデル呼出しだけ成功し、外部検索ツールを呼べない。
- 同時RunでDB、maildrop、ポート、HOMEが共有されない。専用network・mount・tmpfsによる分離を使う。

## 配布フラグと実行時の証拠

`distribution.json` の `isolation_verified: false` は、`prepare_workspace.py` が
ファイルを配布した時点では実行環境の隔離を検証していない、という意味である。
runnerは配布manifestをそのまま `manifest.json` の `distribution` に取り込むため、
実装が正常終了してもこの値はfalseのまま残る。Run全体の隔離失敗や、実行時の設定が
未適用だったという判定値ではない。配布記録は実行後にtrueへ書き換えない。

確認対象と参照先は次のように分かれる。

| 対象 | 証拠ファイル | 証拠の範囲 |
|---|---|---|
| 自条件の入力と共通指示 | 各Runの `manifest.json` → `distribution.files`、元の `distribution.json` | 配布許可リストと入力SHA-256。実行時のアクセス拒否は証明しない。 |
| 当該Runの実行設定・制御コード | 各Runの `manifest.json` → `environment` / `management`、`management-source/run_codex.py` / `run_experiment.py` / `model_gateway.py`。補助記録があるRunでは `management.json` | imageとgatewayの固定版、専用network、mount、HOME、検索制限等の設定と適用するコードを追跡する。 |
| 起動時のnetwork構造チェック | 上記の `management-source/run_experiment.py` とRunの終了記録 | runnerは起動前にDocker networkをinspectし、Internal、Run IDラベル、gateway mode=isolatedを検査し、不一致なら起動しない。ただしinspectの生結果を各Runへ保存する実装ではない。 |
| 当該Runのモデル通信 | 各Runの `raw-usage/started.jsonl` / `events.jsonl`、`usage.json`、`native-usage.json` | gateway経由の呼出しと利用量。外部アクセス拒否や全隔離境界の証明ではない。 |
| 終了と提出固定 | 各Runの `manifest.json` → `processes_stopped` / `submission_fixed`、`snapshot.json` | コンテナ停止確認と提出ソース固定。アクセス境界の代用ではない。 |
| 環境のアクセス拒否校正 | [gateway-isolation-integration.json](gateway-isolation-integration.json)、[isolated-host-service-integration.json](isolated-host-service-integration.json) | 管理資料カナリア、GitHub等、hostサービス、gatewayの禁止経路に対する独立probe。各実装Run自身で採ったカナリア記録ではない。 |
| 終了制御とモデル通信の校正 | [protocol-integration.json](protocol-integration.json)、[model-smoke-integration.json](model-smoke-integration.json) | 実Dockerの正常・異常・上限終了と子プロセス停止、および指定モデルとの小さな実通信。 |

実装Runは `results/runs/<Run名>/` に記録する。例えばpilot normalの配布フラグの解釈も上表と同じであり、
`manifest.json` のfalseを校正結果と混ぜて集計しない。
`management.recorded_after_start: true` があるRunは、制御コードの対応を開始後に記録したことも
明示している。これを起動時に採取した証明やDocker inspect結果と読み替えない。

現時点の限界は、各実装Runの完全なDocker inspect結果、各Run専用の全カナリア結果、
2本の実装Runを同時に走らせたDB・maildrop・HOME相互アクセス試験を保存していない点である。
実行時の必須構造チェックと共通環境の独立校正は実施しているが、
「全境界を全Runで実測済み」とは報告しない。より強いRun単位の監査証拠が必要な場合は、
既存入力や過去manifestを書き換えず、別の実行時証拠ファイルとして追加収集する。

2026-09-05の初回Windows環境確認ではdaemonへの接続は失敗したが、WSL UbuntuのDockerは利用できた。
`protocol-integration.json` は実Dockerでoffline境界、正常/実エラー/timeout、子プロセス停止を検証した証拠。
モデルgateway通信とgateway境界は別途実測する。offline境界の成功をgateway境界の証拠に流用しない。
`gateway-isolation-integration.json` で4種hostカナリア、GitHub/raw GitHub/直接IPへの接続拒否、
任意gateway URL、Web検索tool、モデル変更の拒否を実測した。
`model-smoke-integration.json` で指定モデルの通信とusage照合も確認した。
仕様と共通指示はworkspace mountに加え個別readonly mountし、実装中の変更をOSで拒否する。
`offline-runtime-integration.json` は同じworker imageでEF Core Sqliteのrestore/native query、
npm ci、.NET HTTP5080、Vite HTTP5173とReact変換を実測した校正結果。
runnerはRun専用HOMEのNuGet sourcesを空にし、npm offline設定と書込み可能な一時cacheを準備する。
依存取得はimageの事前cacheに限定される。追加ライブラリを必要とするなら全条件共通imageを
事前更新し、環境版を上げてから実装をやり直す。片条件の実行途中で依存を追加しない。
モデルの事前知識に公開資料が含まれる可能性はこの境界でも除去できない。
公開manifestへ認証情報、環境変数全文、CLI生出力を入れない。

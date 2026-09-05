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
単にnetwork有効にすることを隔離の代替としない。gateway導入後も次の実測をRun開始前に保存する。

- 対条件、管理AGENTS、採点器、過去Runのhostカナリアが読めない。
- GitHub/公開repo、任意外部URL、ホストサービス、別Runへ接続できない。
- モデル呼出しだけ成功し、外部検索ツールを呼べない。
- 同時RunでDB、maildrop、ポート、HOMEのカナリアが共有されない。

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

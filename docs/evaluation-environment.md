# 独立E2EのLinux実行環境

公開helper `evaluation/prepare-app-container.py` は採点ケースを含まない。
WSL Dockerホストから固定Runと研究者専用Linux評価器のパスを指定して実行する。

```sh
python3 evaluation/prepare-app-container.py /research/run /research/private-eval-linux \
  --evaluator-image mcr.microsoft.com/playwright@sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d
```

停止済みappコンテナとresearcherコンテナ、専用internal networkを作成し、IDとconfigパスを返す。
networkのbridge gateway modeはisolated。hostポートは公開せず、researcherが同じnetwork内の
appの固定IPへ接続する。Viteのhost名制限を避けるため、任意の名前を許可する設定変更はしない。

`docker start -a <researcher_container>` で研究者側の `run.mjs` を実行する。
評価器がappをstartし、固定仕様の手順で起動してから採点し、最後にappをstopする。
アプリはfrozenをread-onlyでmountし、/tmp/appへコピーしてビルド・起動する。
専用maildropだけをhostへ書ける。rootはread-only、非root、capabilitiesなし。
private評価器・Docker socket・認証情報をappへmountしない。

研究者コンテナだけがDocker socketとDocker CLIを持ち、private root、frozen、snapshot、maildropを
同じ絶対hostパスで参照する。private rootはread-only、当該評価の出力ディレクトリだけread-write。
これは研究者の権限であり、appの権限ではない。hostのfirewallや共有サービス設定は変更しない。

使用するprivate rootには凍結済み評価器ファイルとLinux `npm ci` の結果、
`tools/node`（Node 22.23.2）が必要。Windows側のnode_modulesを上書きしない。
researcher imageにはNode 24が含まれるため、helperは明示的にtools/nodeを実行し、
resources.jsonへバージョンと実行ファイルSHA-256を記録する。
Playwright 1.58.2 / Chromium 145.0.7632.6でDOM読取りを実測済み。

評価後は保存されたresources.jsonの3つの名前だけを使い、
`docker rm <researcher_container> <app_container>`、`docker network rm <network>` で後片付けする。
他のRunや共有コンテナを一括停止・削除しない。再評価は同じfrozenから新しいhelper実行で別evaluation_idを作る。

`isolated-host-service-integration.json` はhost上のcanary listenerを使って、
host interfaceとbridge addressのどちらからもアプリと同じisolated networkでは接続できないことを確認した証拠。
private評価器の詳細結果・ログ・スクリーンショットは公開repoへコピーしない。

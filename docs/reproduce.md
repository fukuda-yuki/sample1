# 再実行手順

研究管理側はこのリポジトリと、権限を分けた非公開評価器・Run保管先を持つ。実装Runへこの手順を配布しない。WSL Ubuntu内のDocker 29で動作を確認した。Windows側Docker Desktopへの接続失敗とWSL側の成功を混同しない。

## 環境と版

現在の固定設定は [experiment.json](../config/experiment.json)、予定順は [execution-order.json](../config/execution-order.json)、入力hashは [version-manifest.json](../config/version-manifest.json)。乱数化の結果は今回全ペアnormal→antiとなった。観測前に生成した順序を都合よく引き直さない。

実行用imageはlocal content IDで固定している。[runtime-archive.json](runtime-archive.json) のhashと照合して `docker image load -i results/runtime/sample1-worker-exp-001.tar` で復元できる。archiveは大きいためGitへ含めない。新規構築する場合は `docker build -f scripts/Dockerfile.worker -t sample1-worker:local scripts`。再buildで異なるimageになったら同一環境と仮定せず、版と実測を更新する。業務骨格と資格情報はimageへ入れない。

## 実装

現在はexecution-scope.jsonにより新しい実装Runの設定生成・開始を拒否する（pilotの再実装も含む）。以下は将来ユーザーが再開範囲を明示した後のDockerホスト上の操作例。`/research` は研究者専用の作業先へ置き換える。既存の出力先は再利用しない。実行設定・入力の生成は初回だけ行い、同じ固定版で繰り返す。

```sh
python3 scripts/prepare_workspace.py normal /research/distribution-normal
python3 scripts/prepare_workspace.py anti /research/distribution-anti
python3 scripts/make_run_config.py pilot-1-normal /research/pilot-1-normal.json
python3 scripts/run_codex.py /research/distribution-normal /research/pilot-1-normal.json /research/pilot-1-normal --auth /research/auth.json
```

`--auth` は既存ChatGPTログインのauth.json。ファイルを表示・公開せずgatewayだけにread-onlyでmountする。実装workerには渡さない。実モデルの利用可能性は [model-smoke-integration.json](model-smoke-integration.json) に実測を保存しているが、各アカウントの権限や期限は別途必要。

pilot-1-anti、comparison-1-normal等は予定manifestにある名前を `make_run_config.py` に渡し、対応する条件のdistributionを指定する。比較は [pilot-plan.md](pilot-plan.md) の開始ゲートを満たしてから行う。失敗を取り直す場合は元Runを残して新規出力先・rerun_ofを使う。

`manifest.json` の終了理由・processes_stopped・submission_fixedを確認する。停止未確認を無理に採点しない。`snapshot.json` とfrozenが提出物、raw-usageとusage.jsonが数値原本と集計。モデルの生の思考・認証情報は収集対象にしない。

## 独立採点

採点コードの保管場所とLinux準備は [evaluation-environment.md](evaluation-environment.md) を参照。公開Gitだけには非公開E2Eのコードを含めないため、研究者が保管した凍結評価器が必要。各評価のevaluator-snapshotがcode・設定・台帳・lockfileの原本を持つ。

```sh
python3 evaluation/prepare-app-container.py /research/pilot-1-normal /research/private-eval-linux --evaluator-image mcr.microsoft.com/playwright@sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d
docker start -a <返されたresearcher_container>
```

評価器が別コンテナの提出アプリを標準起動し、58ケースを57IDへまとめる。結果・traceは研究者用private rootへ保存。評価後は返されたapp/researcherコンテナと専用networkだけを削除する。評価器障害による再評価は同じfrozenに対して新しいevaluation_idで行う。実装を手直ししない。

## 集計・図

研究者側に、全Runと明示的に選んだ採点実行の対応をJSON配列で保存する。未採点Runも `evaluation_directory: null` として入れる。

```json
[{"run_directory":"/research/pilot-1-normal","evaluation_directory":"/research/private-eval-linux/evaluations/<id>/result"}]
```

```sh
python3 -m pip install -r analysis/requirements.txt
python3 analysis/collect_runs.py /research/selections.json /research/aggregate --validity /research/private-eval-linux/evaluation-validity.json --ledger /research/private-eval-linux/evaluations/<id>/result/evaluator-snapshot/requirements-ledger.json
python3 analysis/plot.py /research/aggregate/runs.csv /research/aggregate/tokens-quality.png
```

phase・実験版・採点版が違う図は分ける。欠測値を0にしない。図の横に `<図名>.missing-runs.csv` が生成され、全Runの表・ID別判定・選択した採点実行のhashへ辿れる。

## 整備物の検証

```
python evaluation/validate-requirements.py
python -m unittest discover -s scripts -p 'test_*.py'
python -m pip install -r analysis/requirements.txt
python -m unittest discover -s analysis -p 'test_*.py'
```

合成集計の再生成は `python analysis/calibrate.py <新規出力先>`。これは効果比較のデータではない。Dockerの隔離・通常起動・モデル接続・独立E2Eの実測結果と、Python検証の成功を区別する。

## 採点有効性の正本

研究者専用 `../sample1-private-eval-linux/evaluation-validity.json` が採点実行ごとの有効性の正本。集計の `--validity` は必須であり、選択JSONには有効・無効を指定しない。schema_version=1、attempts配列の各記録は evaluation_id、run_id、status（valid/invalid/pending）、reason、submission_hash、evaluator_hash、summary_hash、results_hash、adjudications（原本への相対pathとsha256）を持つ。同じIDを重複させない。

旧adjudicationは上書きせず参照する。旧記録にRun IDがない場合だけ、legacy_adjudication_bindingに当時のresearcher-configのconfig_pathとconfig_sha256を保存し対応を検査する。途中停止でsummary/resultsが未生成の記録はハッシュnullを残すが、完全な採点として取り込まない。これらは未採点として選択し、元の無効理由は公開停止記録と有効性台帳に残す。

記録なしはpending。invalid/pendingはraw結果が満点でも品質・全件合格をnullにする。raw件数・版・品質の整合性検査は省略しない。invalid原本を参照したままvalidに変更することはできず、同じ提出物の新しい採点実行で判断する。validは校正成功だけでは付けず、実際の採点と根拠を研究者が確認して記録する。CSV・項目内訳のpass/failはraw判定であり、有効性列がvalidでない限り実装品質とは解釈しない。

## 原本欠落後の更新

D009と[保全手順](preservation.md)が現在の再開手順。旧Runの再採点待ちは終了し、保管パッケージからの復元試験成功後のみpilot-2を順次実行する。上記pilot-1の開始例は過去手順であり現在は許可しない。共通imageは保管パッケージのruntime/images.jsonとtar実体から復元する。Run・評価器・usageを作業領域なしで回復できる証拠を必要とする。

D010適用後はallowed_startsが空で、pilot-2も再開しない。normalの失敗とanti未開始、ネットワーク隔離修正後の復元試験合格は[pilot-2結果](pilot-2-results.md)を参照。新規実装取得には別のユーザー判断が必要。

D011のレビュー対応は修正・非モデル検証まで。[保全手順](preservation.md)に現行台帳の開始判断と固定入力診断の入口を記載した。診断の個別許可も空で、実モデルを呼ばない。今回の検証範囲・限界は [レビュー対応検証](review-code-verification.json) と [WSL接続・隔離検証](review-network-verification.json) を参照する。旧復元証拠は履歴として保持し、新コードでのフル復元・校正成功を意味しない。

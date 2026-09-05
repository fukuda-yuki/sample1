# パイロット結果と停止地点（2026-09-06）

**品質は両条件とも未確定。評価器・集計・停止制御の修正を実施したが、固定原本の欠落により同じ2提出物の再採点は未実施。** 2026-09-06の現物確認では両Runのfrozenは空、manifest.json・snapshot.json・usage.json・native-usage.jsonも存在しない。ユーザーから別保管先なしとの回答を得た。workingを固定提出物として代用せず、新しい実装Runも開始していない。追加比較は0 Run。進捗の正本は GitHub [#1](https://github.com/fukuda-yuki/sample1/issues/1)・[#11](https://github.com/fukuda-yuki/sample1/issues/11)。

以下の使用量・終了状態は過去の公開照合記録であり、今回原本から再確認した値ではない。

| 条件 | 実装終了 | 時間 | 総トークン | requests | 使用量欠測 | 品質 / 全件合格 |
|---|---|---:|---:|---:|---|---|
| normal | agent_completed | 1,341.24秒 | 5,798,122 | 75 | なし | 未確定 / 未確定 |
| anti | agent_completed | 1,315.25秒 | 4,754,779 | 60 | なし | 未確定 / 未確定 |

[CSV](pilot-artifacts/pilot-runs.csv)・[原本対応とhash](pilot-artifacts/pilot-provenance.json)・[usage照合](pilot-usage-reconciliation.json)。過去の照合記録では総量は全リクエストのinput+outputで、CLI原本と一致していた。cached inputとreasoning outputは内数であり再加算しない。両Runのプロセス停止・提出物固定と採点前後の提出物全hash一致も過去の記録であり、現在の原本保持を保証しない。実装終了は要件充足の証明ではない。

![使用量と品質の停止時点](pilot-artifacts/pilot-summary.png)

[X=総トークン、Y=固定57ID充足率の図](pilot-artifacts/pilot-tokens-quality.png)では、品質のない2 Runを点にせず[欠測表](pilot-artifacts/pilot-tokens-quality.missing-runs.csv)に残した。品質未確定を0点・57件の実装失敗・全件不合格に読み替えない。この各1回からAP-001の品質効果やトークン差の原因を推定しない。

## 前回の校正と停止理由（履歴）

評価版 `87b50d07cdcaae89ebc657ffc87ac860b5f0b3062a7d314c59ff19fdf3eca291` で、標準・独立UI変種・別名マップ変種はいずれも57/57、診断5/5。閾値を50万円に変更した変異は44/57（13件失敗）、診断2成功/3失敗。[校正概要](../evaluation/calibration-summary.json)は旧版の結果を新しい版の測定と混同せず、各hashを保存している。

実パイロットの再採点では、[公開F-001](../normal/spec.md)が管理者代理登録または公開フォームの自己登録を認めるのに、評価器が管理者ログイン後のユーザー管理内登録だけを要求していた。両提出物は未ログイン画面から自己登録を提供している。評価器は登録入力前に止まっており、登録機能が失敗する証拠にはならない。研究者用test_items/ledgerの管理者前提を公開仕様の代わりに扱った監査漏れが原因。前回はそれ以上の修正・再採点を行わず停止した。今回の修正と区別する。

以前の起動helper障害とUI構造依存の採点も無効として保全済み（[起動障害](pilot-evaluation-infrastructure-incident.json)、[UI障害](pilot-ui-contract-incident.json)）。最新の2試行は `invalid_evaluation_registration_path / effective_quality=null`。原本のraw・trace・スクリーンショットを変更せず、別adjudicationで無効理由を残した。

## 保管先

作業ルート: `C:\Users\mwam0\Documents\ls\sample1`。下記はこのルートに対する相対パス。

| 条件 | Run ID | 固定提出・usage | 今回の無効な評価ID |
|---|---|---|---|
| normal | 250df4e7-f8f9-44cd-8324-db24e050962f | results/runs/pilot-1-normal | 722b27ba-940d-4f6e-9f2d-a27094cdbceb |
| anti | e849b8d9-60e2-464f-bea9-11d24134674f | results/runs/pilot-1-anti | b228155a-fe0d-4bd7-9b85-81bf59934350 |

上表は過去に記録した保管先。現在はfrozen内のファイルとRunメタデータが欠落しており、保持済みとは扱えない。非公開評価器は `../sample1-private-eval/`、Linux実行側は `../sample1-private-eval-linux/`。後者の `evaluations/<評価ID>/` にconfig、凍結評価器、raw/trace、adjudication、停止前後inspectを保存。自己登録の詳細根拠は前者の `calibration/pilot-registration-entry-audit.json`。privateフォルダと大きな実行原本・image archiveは公開Gitへ含めていないため、このローカル保管先も再開に必要。

## 次回はここから再開

1. #1・#5・#7・#10・#11の最新状態を確認する。現在は固定原本欠落が再採点の阻害要因。
2. 原本が発見された場合だけ、過去の公開hashと照合して同じ固定提出物であることを確認する。workingから原本を推定再作成しない。
3. 原本を回復できた場合は新しい共通評価版を使い、新しい評価IDで採点する。別の評価器問題が見つかったら品質nullと証拠を保存して再び停止する。
4. 採点有効性台帳を確認した通常集計で表・図を更新する。現在の表は原本からの新規集計ではなく、過去公開値と最新の欠落状態を合わせた引継ぎ資料。
5. 原本が回復できない場合、新規Runで置き換えるにはユーザーの新しい判断が必要。現在のexecution-scopeはpilot再実装を含む全新規開始を拒否する。比較6 Runも開始しない。

図の再生成は `.venv/Scripts/python.exe analysis/pilot_snapshot.py docs/pilot-artifacts/pilot-runs.csv docs/pilot-artifacts/pilot-summary.png` と `analysis/plot.py` の同CSV入力で行える。`pilot_snapshot.py` は今回の「過去usage記録保持・原本欠落・品質未確定」状態専用であり、品質が確定した後は通常の `plot.py` を使う。


## 今回の修正と検証

57IDの必須結果・許容方法・便宜操作を分離し、登録機能とユーザー作成前提を修正。別UI校正で発見した番号重複表示による件数誤判定も修正した。新評価版 `7bbfb2423cde28c9a7b0b6a62ac3731fe5be6c64336918c83b698bb02722ae45` で管理者登録・自己登録・別UIは各57/57、両登録経路の50万円変異は各44/57（13失敗）、重複メール変異は56/57（T-001-02で検出）。Linux実Dockerの自己登録fixtureも57/57で、アプリから非公開評価コード・Docker socketを読めないことを確認した。これは校正結果でありpilot品質ではない。

集計・描画25 tests、停止・実行管理23 tests、ブラウザ解決器3 tests、57ID/AP-001検査を通過。無効化台帳への11旧試行の対応付けはvalid 0件として保存。詳細は[今回の検証記録](evaluator-repair-verification.json)、[校正概要](../evaluation/calibration-summary.json)、[有効性台帳の概要](../evaluation/validity-registry-summary.json)。失敗校正を削除せず、各版を区別した。

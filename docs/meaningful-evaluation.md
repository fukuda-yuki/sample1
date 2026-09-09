# 検証の意味を確認する実行手順

本手順は #25〜#34 の新形式に適用する。実施結果と受入状態は [親Issue #26](https://github.com/fukuda-yuki/sample1/issues/26)を正本とする。スクリプトやテストの存在だけでは、新規normal/antiの実測完了を意味しない。

## 固定するもの

57 ID・58必須ケース・等配点・固定分母57・AP-001を維持する。要求原子とケース/assertion/helperの対応、未測定範囲、校正の正例・負例の期待集合は研究者用の私的監査資料に置く。実装役へは自条件のspecと生成したRUN_CONTRACTだけを渡す。

`batch_schema=2`, `contract_version=2` は明示的な新版であり、旧計画を暗黙に変換しない。共通契約のモデル・effort・実装時間・子agent方針は設定から生成し、開始認可と配布hashを照合する。旧提出物は実際に配布された旧契約で解釈する。

## N / K / limit

Nは各条件の予定回数、Kは合計同時実装数、limitは今回のdispatchで新たに開始できる上限。計画作成はモデルを呼ばない。以下は研究者が設定・証拠・開始許可を準備した後の例である。

```sh
python3 scripts/copilot_batch.py plan /research/new-batch --config /research/config.json --repetitions-per-condition 1 --max-parallel 2 --seed 123
python3 scripts/copilot_batch.py check /research/new-batch
python3 scripts/copilot_batch.py run /research/new-batch --locator /research/monitor.json --secret-file /private/go-key --execute-real-model --limit 2
python3 scripts/copilot_batch.py status /research/new-batch
python3 scripts/copilot_batch.py set-parallel /research/new-batch --max-parallel 1
```

実装子プロセスだけが並列に動き、monitor取込・共有台帳・採点は直列に処理する。K縮小時は実行中Runを打ち切らず自然減を待つ。停止中dispatchへのset、古いdispatchの制御、不正な整数は拒否する。開始直前にUUIDとassignmentを不変記録し、不確かな開始を未開始に戻さない。

中断回収はモデル鍵もモデル開始許可も不要な別入口で実施する。復元可能な所有記録を照合して停止・固定・保全し、同じUUIDを回収する。

```sh
python3 scripts/copilot_batch.py recover /research/new-batch --locator /research/monitor.json
python3 scripts/copilot_batch.py resume /research/new-batch --locator /research/monitor.json --secret-file /private/go-key --execute-real-model --limit 1
python3 scripts/copilot_batch.py extend /research/new-batch --repetitions-per-condition 3
```

`recover`は未開始枠を実装しない。`resume`の新規開始数もlimitで制限される。extendは停止中のみ、既存予定のprefixを保持してNを増やす。追加枠の開始には、その枠を含む明示的な認可が必要である。古いlockを手で消して実装をやり直さず、所有情報に基づく回収入口を使う。

## 通信と503

OpenCode GoのMuse 1.2/1.3 ContributorはResponses、Omen Alpha/MiMo-V2.5はChat Completionsを使用する。ユーザー環境変数`OPENCODE_GO_API_KEY`から用意した秘密ファイルはgatewayだけに渡す。worker、ログ、Issue、保全対象には鍵を含めない。

`model_http_503_policy=stop_run_and_cleanup`では、上流HTTP503のヘッダー受信時点でそのRunの新規送信を停止する。停止確認→原本固定→保全検証→所有ID確認済み資源とworkingの削除、の順を守る。429/500/504やアプリ画面の503文字列をこの条件へ読み替えない。停止・保全・所有確認に失敗した場合は削除せず、未開始枠を保持する。

今回の承認では失敗条件だけを1.3→Omen→MiMoの順で別Run・別設定版に切り替えられる。各候補1回、成功済み条件は再生成しない。異なるモデルの結果はツール受入の証拠であり、normal/antiの効果比較には使わない。

## 採点と妥当性

```sh
python3 scripts/copilot_batch.py evaluate /research/new-batch --pending --private-root /research/private-eval --evaluator-image <digest> --validity /research/private-eval/evaluation-validity.json
python3 scripts/copilot_batch.py evaluate /research/new-batch --slot normal-001 --private-root /research/private-eval --evaluator-image <digest> --validity /research/private-eval/evaluation-validity.json
python3 scripts/copilot_batch.py export /research/new-batch --validity /research/private-eval/evaluation-validity.json
```

明示的な再採点は新評価UUIDを作り、同じ提出hashと旧評価履歴を残す。中断された同じ評価jobの再開は同じUUIDを維持する。結果schema2は実行完了後も審査中であり、業務上の期待・観測・操作・画面/trace・前提波及の照合を経た妥当性裁定が必要になる。

raw pass/fail/blocked/errorは変更しない。原因分類、業務assertion到達、機能別点、直接検証範囲、前提不成立、評価側判定不可、未確認を別列で示す。raw failから実装責任を自動推定しない。旧記録にない到達情報はunknown、未採点は点数null、有効な0点は0とする。usage完全性も独立状態であり、欠測を0tokenへ置き換えない。

研究者用evidence-indexは要求・操作・期待・観測・証拠hashを結ぶ。合格も操作記録と終端画面を残し、非合格はtraceも必要とする。裁定は原本を改変せずhash付き依存として追記する。公開CSV/JSON/SQLiteと図では同じ有効性・欠測理由を使い、私的画面やログを配布しない。

## 変更に対応する検証と保全

`scripts/verification_plan.py`は変更依存から必要な検証・時間目安・待ち理由・再利用可否を出す。300秒以下の非採点smokeと全校正は別である。関連する契約、コード、lock、browser、image等のhashが違う証拠を再利用しない。

評価版を変更した場合は事前期待を固定した校正を通し、同じ両提出物を新評価UUIDで再採点する。標準構造と複合構造はそれぞれ同じfixtureを計3回、旧両提出物と新両提出物はそれぞれ2回を照合する。得点上昇や満点を成功条件にしない。

`scripts/copilot_analysis_archive.py`の明示的許可リストを保全と不変性検査で共用する。working/node_modulesを全走査しない。元batch・private原本・保管庫・現行管理コードを読めない復元側でCSV/JSONとSQLite全5表を再生成し、元の集計と照合する。中断コピーは所有記録を確認して保持し、新しいコピーで復元を再開する。完全な復元物の改変は拒否する。

開始前の`meaningful-evaluation-readiness`パッケージには、契約、並列回収、通信、monitor、校正、同一提出物再採点、実Run復元再集計、runtime復元、独立レビューの根拠を保存・復元し、今回の設定・管理コード・評価版へhashで結び付ける。非モデルの受入を実モデルの成功と呼ばない。開始後も各新Runの実装・usage・monitor・採点・裁定・保全・復元を実測する。

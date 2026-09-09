# Run単位の集計と図

主軸はユーザー確定の総トークン量 × 非公開E2E項目充足率（%）。1点=1 Run、Y=100×合格ID数/57。T-006-05の2入力は両方成功して1点。アサーション分割で重みを増やさない。全件合格booleanも別列へ保存する。自主テスト・矛盾報告・人格は採点しない。

## 入力と状態

analysis/aggregate.pyは固定台帳、Runリスト、評価JSONLを読み、runs.csvとtest-results.jsonlを出力する。各Runはrun_id、phase（calibration/pilot/comparison）、condition、experiment_version、score_version、submission_hash、end_reason、usage_complete、total_tokensを持つ。評価行はrun_id、evaluation_id、case_id、status、evidence、score_version、submission_hashを持つ。

- pass: 必須ケース全成功。fail: 期待した観測との不一致（実装責任の確定ではない）。blocked: 起動・認証・前提不成立で後続へ到達不能。raw fail/blockedは分母57に残り、妥当性裁定と原因は別に記録する。
- error: 評価器・評価インフラ障害。1項目でもerrorならその採点の品質値はnull。同じ提出物を新しいevaluation_id（採点実行ID）で再評価し、旧結果も保存する。
- 欠けた評価ID/必須ケースはblockedとして保存し、自動的に分母を減らさない。ただし評価器の途中クラッシュと分かっている場合はRunのevaluation_errorに理由を設定し品質値をnullにする。
- usage_complete=falseまたは利用量nullはXをnullにし、図とは別の欠測表へ残す。既知下限を確定総量にしない。
- 採点前のブラウザ起動障害などでsubmission_hashがnullでも、評価器障害Runとして保持する。未採点を明示する場合は選択ファイルのevaluation_directoryをnullとし、品質もnullにする。未採点のRunを実装不合格57件へ置き換えない。
- 上限到達・実行失敗・未完了も提出物があれば独立採点する。条件ごとに成功Runだけを選ばない。

未知ID・不正状態・異なる版/提出物hash・同一case_idの重複は入力エラーとして拒否する。診断ケースは別ファイルに置き分母へ入れない。AP-001関連区分は台帳の事前区分を保存し、結果を見て重みを変更しない。

collect_runs.pyはRun manifest・usage・選択した採点実行のsummary/resultsを結合する。summaryのledger_hashと指定した凍結台帳のバイト列hash、58必須ケースの完全性、summaryの件数・品質とケース集計の一致も検証する。途中で切れたresultsファイルを暗黙のblockedへ変換しない。古い採点版は対応する凍結台帳を--ledgerで指定し、現在の台帳で再解釈しない。

CSVには採点実行ディレクトリ、台帳・manifest・usage・resultsのhashを残す。採点実行IDはディレクトリで識別し、T-XXX-YYのevaluation_idとは区別する。元Run/採点ファイルは変更しない。出力CSV/PNGは再生成可能な派生成果物なので同じ出力先を指定すると置き換わる。異なる選択の比較を保存するときは出力先を分け、使用した選択JSONも保存する。

## 再生成

```
python analysis/aggregate.py --runs <runs.json> --results <evaluation.jsonl> --out <output>
python analysis/collect_runs.py <selections.json> <output> --validity <current-validity.json> --ledger <frozen-ledger.json>
python -m pip install -r analysis/requirements.txt
python analysis/plot.py <output>/runs.csv <output>/tokens-quality.png
python -m unittest discover -s analysis -p "test_*.py"
```

## Chart contract

問いは同じ版・同じphaseのRunで消費量と項目適合がどこに位置するか。散布図だけで因果効果・モデル順位を主張しない。出力は再実行可能な研究用静的PNG（Matplotlib）、12×7インチ。Xは総トークン、Yは0〜100%、固定分母57。conditionはblue/orangeの二色、normalは塗りあり・antiは塗りなし、終了理由は形で区別しRun IDを添える。無効な座標は0にせず図外の理由表へ、件数を図に表示する。

pilot各1回は小標本で差の確定値ではない。予定数以上にデータを水増しせず、疎な図にも実測点を全て残し正確な値はCSVで併記する。phaseと実験版・採点版を跨いで平均を作らない。校正の合成データは明示して実測比較に混ぜない。PNGを開いて軸・凡例・文字・欠測表示を確認する。

図ごとの欠測表は `<図名>.missing-runs.csv` として保存する。異なる図を同じフォルダへ保存しても、以前の図の欠測表を上書きしない。採点版がない未採点Runは品質nullのまま欠測表へ含める。NaN/Inf、負の座標、100%を超える品質、重複Run IDは不正入力として拒否する。

集計器の実JSON形式との接続検証は [analysis-integration.json](analysis-integration.json) に保存する。実際に完了した校正の58ケースを使い、Run manifestのみ合成、usageは明示欠測として57ID・品質100%・トークンnullへ集計できた記録である。実装モデルの実測トークンや比較効果の結果ではない。再現には記録内のsynthetic_manifest/usageを一時Runディレクトリへ保存し、snapshot_sourceをsnapshot.jsonへコピーして、sourceをevaluation_directory、ledger_sourceを--ledgerへ指定する。


2026-09-06以降、実装Runの取り込みはkind=evaluationと採点有効性台帳を必須検査する。上記analysis-integration.jsonは旧実装の接続検証履歴であり、calibrationをpilotへ取り込む手順は現在拒否される。校正は専用の校正概要または明示的な合成校正として分離する。aggregate直接利用でも有効性証拠が欠ければ品質nullになる。invalid/pendingのraw判定件数を有効品質と解釈せず、CSV・内訳の有効性と理由を参照する。


## 測定情報の拡張（2026-09-10候補）

旧JSONLのraw statusと57 ID／58ケースは保持する。measurementがない旧記録の到達段階はunknownであり、passから業務assertion到達を推定しない。新版は操作対象探索、操作、初期化、業務assertionを分け、前提スタックと原因eventへの参照を保存する。stageは実行境界、responsibilityは責任裁定であり、探索失敗だけで評価器不備とも実装不備とも断定しない。

coverage_jsonには機能別のID合格数、raw充足率、有効充足率、直接assertion到達ケース数、前提不成立、評価側未確定、旧版unknownを記録する。機能別の割合を合算して新しい重み付き総合点を作らない。総合点は有効裁定がある場合のみ固定分母57で表示する。

coverage schema2は裁定済みの責任と影響を表示に反映する。実装または指示が原因と確認された対象探索失敗を、評価側未確定へ重ねて数えない。裁定のimpact=prerequisiteは、raw failのままでも前提不成立として区別する。根拠のある先行評価IDと要求への参照を保存し、該当する先行テストがなければID配列は空にする。観測イベントへの参照を持たない前提裁定や、存在しない評価IDへの参照は拒否する。裁定のない旧記録の原因・到達は推定しない。

evaluation_attempted / evaluation_completed / measurement_state（not_attempted、pending、valid、invalid）はusage_completeと独立。未採点の件数を57 blockedへ置き換えず、集計列はnull。X欠測でも有効Y=0は保存する。schema2の採点実行完了は自動validにせず、要件対応と操作・画面・trace・ログの証拠索引を研究者が確認して裁定を追加する。

固定提出物の原本が現在見つからない場合、公開exportのsource_availabilityはmissing、measurement_stateはunavailable、有効品質はnullにする。過去のevaluation_validity裁定とraw件数は保持する。これは現在の証拠の利用可能性であり、過去の有効裁定を無効裁定へ書き換えるものではない。原本hash不一致は別の改変エラーとして拒否する。

再採点では元提出物と旧選択を保全し、新評価UUIDの選択を別batchまたは明示的なselectionへ保存する。評価器を変更した場合は同じ両提出hashを使用する。実装契約の説明を旧提出物へ遡及適用しない。

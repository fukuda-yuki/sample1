"""Write the explicit manuscript-to-SQL and saved-evidence index."""
from pathlib import Path
import json

BASE=Path(__file__).resolve().parent
claims=[]
def claim(id,statement,query=None,files=(),method='',limits='',text=()):
    claims.append(dict(id=id,statement=statement,query=query,evidence_files=list(files),
                       calculation_or_selection=method,limits=limits,required_text=list(text)))

claim('R01','追加40件、累計60件の取得と、合格率を観測できた57件を区別する。',
      'C02_population_and_validity',['data/runs.csv','data/sql-evidence.json','source/additional/retention.json'],
      '各バッチ・条件の開始数、score_available、裁定を集計。全モデルは1.2。',
      '評価出力の保存完了は製品品質の妥当性確定を意味しない。', ['累計60件','観測対象は57件'])
claim('R02','追加2,280 ID・2,320ケース、累計3,420 ID・3,480ケースを保存した。',
      'C11_case_count',['data/ids.csv','data/case_results.csv'],
      '生の評価出力を57 ID、58ケースで照合。3起動不能Runの174ケースは雛形として保持。',
      '保存行数を実行済み業務判定数にしない。', ['2,280 Run×ID','3,480ケース','3,249件'])
claim('R03','累計記録済み総トークンは482,034,106、平均合格率は通常67.5%・不整合46.5%。',
      'C01_condition_statistics',['data/summaries.csv','data/runs.csv'],
      'stratum=cumulative。トークンは各30件のobserved_tokens。合格率は通常28件・不整合29件の平均合格ID÷57。',
      '起動不能3件の合格率は欠測。有効品質はnull、元の完全性フラグは維持。',
      ['482,034,106','通常67.5%','不整合46.5%'])
claim('R04','追加通常条件は平均合格IDが下がる一方で中央値が上がり、分布が広がった。',
      'C13_medians',['data/summaries.csv','figures/02-batch-distributions.png'],
      '通常の前回10件と追加18件の合格ID：平均40.2→37.5、中央値40→44.5、標本SD4.756→14.790、範囲31–50→0–51。',
      '前後の取得方式は無作為割付されていない。', ['中央値44.5 ID','追加0〜51 ID','一様に低下'])
claim('R05','完全ペアでは累計の合格率差は不整合−通常−19.8ポイント。',
      'C08_pairs',['data/pairs.csv','data/bootstrap.csv','analyze.py','analysis-policy.json'],
      '合格率が両側で利用可能な27予定ペア。バッチごとに20,000回復元抽出、seed20260911。95% percentile区間−30.669〜−8.967。',
      '57 IDを独立標本とせず、全Runの条件別平均差21.0ポイントとも区別。探索的な複数分析である。',
      ['完全な27ペア','−30.7〜−9.0ポイント'])
claim('R06','平均トークン差の区間は0を含み、1ペアの影響が大きい。',
      'C08_pairs',['data/bootstrap.csv','data/leave_one_pair_out.csv'],
      '累計30ペアのanti−normal平均−2,640,499.47、区間−6,755,980.67〜192,050.62。additional/1除外時−886,857.586。',
      '外れ値を主集計から除外しない。料金や節約の因果効果は推定していない。',
      ['−2.64百万','−0.89百万','28.2%少ない'])
claim('R07','追加取得順の層別でも平均差の大きさは変わる。',
      'C10_order_sensitivity',['data/sensitivity.csv','data/pairs.csv','analyze.py'],
      '前半・後半はバッチ内予定ペア番号、先行条件は保存済み条件順による。追加normal-first−7.368、anti-first−29.825ポイント。',
      '先行条件別は少数ペア、時間や並列化の因果効果を識別しない。', ['通常先行−7.37','不整合先行−29.82'])
claim('R08','不整合条件の累計30件に文書と固定コードの50万円採用がある。',
      'C04_recorded_and_static_thresholds',['reviews/qualitative-review.json','source/additional/qualitative-candidates.json','source/previous/qualitative.json'],
      '前回20件の保存分類を維持。新40件の可視文書と固定コードの引用行を確認。anti追加20件は50万円採用と矛盾記録を確認。',
      '全件の動作を手動確認したという意味ではない。normal追加5件は文書の閾値数値が未確認。',
      ['累計30件で文書と固定コードが対応','合否パターン'])
claim('R09','50万円周辺の保存済み合否パターンは不整合の前回7件・追加14件で一致。',
      'C04_recorded_and_static_thresholds',['data/runs.csv','analyze.py'],
      '事前に指定したT-006-01〜05の6ケースの組合せ。F-006全体は6 ID・7ケースであり、この部分パターンと区別する。',
      '静的確認30件、保存パターン21件、詳細動作記録の個別例を混同しない。', ['7件','14件'])
claim('R10','条件間の平均合格数差のうち13 IDに位置する割合は前回62.5%・追加71.4%・累計67.7%。',
      'C03_dependency_groups',['data/groups.csv','data/sql-evidence.json','analysis-policy.json'],
      '条件ごとの利用可能Run当たり平均合格IDを求め、(通常−antiのdirect差+downstream差)/(全57 IDの通常−anti平均差)。',
      '不均衡な観測数の生合格数差は使わない。原因の寄与率、変更後の回復点数ではない。',
      ['前回62.5%','追加分で71.4%','累計で67.7%'])
claim('R11','不整合が上回る機能もあり、すべての機能が一様に低下していない。',
      'C12_item_gap',['data/features.csv','data/feature_runs.csv','figures/05-feature-heatmap.png'],
      '図はバッチ・条件・機能別の合格ID/(利用可能Run×対象ID数)。追加F-005は通常33.33%・anti50%、F-009は50%・63.16%。',
      'C12は累計のID単位問い合わせ。追加機能別の値はfeature_runsを同じID粒度から集計。',
      ['下書き保存は50.0%','詳細表示は63.2%'])
claim('R12','トークンと合格項目の順位相関に安定した正の関係は見られない。',
      'C09_extremes_and_efficiency',['data/correlations.csv','analyze.py','figures/03-tokens-pass-rate.png'],
      '両値のあるRunを利用し同点平均順位でSpearman。累計normal.06092・anti.06988。個別例normal-011/008/017も提示。',
      '欠測は無作為と仮定しない。消費量を操作していないため因果方向は分からない。',
      ['通常0.06','不整合0.07','normal-011','normal-008','normal-017'])
claim('R13','応答回数と記録済みトークン/HTTP200の双方が平均差に対応する。',
      'C06_responses_and_tokens',['data/response_decomposition.csv','data/runs.csv'],
      '追加HTTP200は通常3,011・anti2,451。各条件総記録トークン/HTTP200と平均回数の積を対称分解。',
      '通常のusage詳細あり応答は3,007。HTTP200の全件にusageがあると仮定せず、モデルの実行速度や料金に換算しない。',
      ['3,011','2,451','3,007'])
claim('R14','記録済み入力が総量の99.3%を占め、その98.2%にキャッシュ明細がある。',
      'C15_token_components_post_hoc',['source/token-components.json','capture_token_components.py'],
      '入力478,693,172・出力3,340,934、cache入力470,088,599。全60件で入力+出力=observed_tokens。',
      '事後の明細分析。cacheは入力の内数であり加算しない。未記録分を補完せず、料金や思考の深さとはみなさない。',
      ['99.3%','98.2%'])
claim('R15','CLI終了コード、完了宣言、管理側の停止理由を区別する。',
      'C07_termination',['data/terminations.csv','source/additional/retention.json'],
      '追加40件はend_reason=agent_completed、exit0=32・137=8、完了宣言後のowned_worker_kill=16。',
      '完了宣言やexit0を標準起動や製品品質の保証としない。', ['32件','8件','16件'])
claim('R16','入口や前提操作の障害が保存済み合格率の低い裾に含まれる。',
      'C05_reachability',['reviews/evaluation-observations.json','data/runs.csv'],
      'OBS-new-normal-003-display、OBS-new-anti-001-login-state、OBS-new-normal-018-blank-entry。画面・通信・固定コードを限定した経路で照合。',
      'normal-018はcompletedのためraw0/57を維持するが、58業務ケース個別の品質不達を確定していない。各タグは重複可能。',
      ['React is not defined','0/57を残す','列を合計して58ケースへ戻す表ではない'])
claim('R17','起動不能3件は異なる保存証拠を持ち、トークンを残し合格率は欠測にする。',
      'C14_unavailable_evaluations',['reviews/evaluation-observations.json','measurement-notes.md'],
      'OBS-new-normal-001-startup、OBS-new-anti-006-excluded-source、OBS-new-normal-016-startup。各UUID/提出hash/評価UUIDと保存ログ・固定ソースを対応。',
      'anti-006のbin除外は配布契約に明記。原本破損やv6バグに置き換えない。アプリ修正・再採点はしていない。',
      ['Vite 5.4.2','vite: not found','@types/react'])
claim('R18','50万円の部長割当が課長の参照権限と通知先の保存結果へ対応する。',
      None,['reviews/evaluation-observations.json','reviews/approval-path.json','figures/06-approval-path.png'],
      'OBS-new-anti-002-approval。T-011-01申請40の課長GET詳細403、別ケースT-014-01申請46の部長宛て1通を区別。',
      '一つの申請の連続traceではなく同Runの二つのケース。差し戻しPOSTには未到達。閾値修正後の合格回復は未検証。',
      ['403','2ケースの記録'])
claim('R19','不整合そのものの純粋な効果や並列化の因果効果は識別していない。',
      None,['analysis-policy.json','source/previous/experiment-design.md','source/additional/experiment.json','report.md'],
      'normalは整合100万円、antiは共通100万円/詳細50万円。整合50万円の第三条件がなく、前後バッチも時期と並列数が同時に変わる。',
      '単一アプリ・モデル・操作・固定評価器に限定する。', ['純粋な影響','並列化の因果効果'])
claim('R20','実装取得144.78分、評価出力保管まで247.62分で、rolling最大5を守った。',
      None,['data/results.json','source/additional/pipeline-events.jsonl','source/additional/retention.json'],
      'results.pipelineのUUID結合された時刻・資源診断。6件目は最初の5件全件回収の45.595分前に開始。',
      '生成と停止・保管の経過時間。直列実験との速度比較や因果効果ではない。', ['144.78分','247.62分','45.60分'])

(BASE/'claim-evidence.json').write_text(json.dumps({'schema_version':1,
    'scope':'Scientific claims mapped to the actual read-only SQLite query outputs and preserved visible evidence. Query names are keys in data/sql-evidence.json; private raw evaluation files remain in the archive.',
    'claims':claims},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Wrote {len(claims)} claim bindings')

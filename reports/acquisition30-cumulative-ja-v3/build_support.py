"""Build the evidence index and supplementary tables for the new two-group report."""
from pathlib import Path
import argparse
from analyze import BASE,read,write_json

MAP=[
 ('C01','60 Run、57 ID/58ケースと、139ファイル・57 CSV記録・900応答の照合',['Q01_population'],['evidence/source-readback.json','evidence/csv-failure-review.json','evidence/request-sources.json']),
 ('C02','条件別の得点欠測・usage欠測・裁定を保持',['Q01_population'],['data/runs.json']),
 ('C03','二群の平均・中央値と独立Run bootstrap',['Q02_group_summary','Q03_medians'],['data/bootstrap.csv','data/summaries.csv']),
 ('C04','得点の範囲、40 ID以上の件数、分布の重なり',['Q10_score_histogram'],['data/score_bands.csv']),
 ('C05','欠測3件の仮想的な範囲計算',['Q01_population'],['data/analysis.json']),
 ('C06','全記録の消費量、中央値・trimmed mean・不確実性',['Q02_group_summary','Q03_medians'],['data/bootstrap.csv','data/summaries.csv']),
 ('C07','最大Runと起動不能Runの消費、除外時の感度',['Q09_extreme_and_low_scores','Q13_unavailable_cost'],['data/sensitivity.csv','data/concentration.csv']),
 ('C08','観測された消費量と合格数、群内順位相関',['Q09_extreme_and_low_scores'],['data/correlations.csv']),
 ('C09','全20機能の分布、逆方向の項目',['Q04_function_results','Q14_other_direction'],['data/features.csv','data/items.csv']),
 ('C10','antiの12 IDとnormalの9 IDの状態列一致',['Q06_identical_status_vectors'],['data/id_results.csv']),
 ('C11','F-011〜F-015の9 IDの合格・fail・blocked',['Q16_nine_workflow_items'],['data/id_results.csv']),
 ('C12','両条件各30件の固定閾値と可視の判断記録',['Q07_threshold_decisions'],['evidence/source-readback.json']),
 ('C13','承認者・表示・画面例外の具体例と低得点Runの到達範囲',['Q09_extreme_and_low_scores','Q11_coverage_by_score_range'],['source/saved-observations.json']),
 ('C14','全57件のCSV失敗分類と1 Runの固定ダウンロード処理',['Q05_all_item_results'],['evidence/csv-failure-review.json']),
 ('C15','入力・出力・cached input、usageを持つ応答数',['Q08_token_components'],['data/statuses.csv','data/analysis.json']),
 ('C16','選択した3 Runの応答ごとの入力と累積',[],['evidence/request-sources.json','data/selected-request-trajectories.csv']),
 ('C17','invalidを除く場合の合格率の感度',['Q01_population'],['data/sensitivity.csv'])
]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,default=BASE/'data');ap.add_argument('--output',type=Path,default=BASE);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    sql=read(a.data/'sql-evidence.json');stats=read(a.data/'analysis.json');runs=read(a.data/'runs.json')
    claims=[]
    for cid,claim,queries,files in MAP:
        assert all(q in sql for q in queries)
        assert all((a.data/Path(f).relative_to('data') if f.startswith('data/') else BASE/f).is_file() for f in files)
        claims.append({'id':cid,'claim':claim,'queries':queries,'query_results':'data/sql-evidence.json','evidence_files':files,
          'scope':'Recorded observations or explicitly labeled exploratory calculation. No new implementation or evaluation; no causal recovery estimate.'})
    write_json(a.output/'claim-evidence.json',{'population':'normal 30 / anti 30, no acquisition strata or matched-Run statistics','claims':claims})
    out=['# 補足：二群の全Runと探索的計算','', '全Runを条件ごとに掲載する。識別子はUUIDに由来し、行どうしに対応関係はない。記録済みトークンは欠測評価のRunも含む。','']
    for c,title in [('normal','通常（normal）30件'),('anti','不整合（anti）30件')]:
        out+=['## '+title,'','| Run | 記録済みトークン | 合格ID / 57 | 合格率 | 評価出力 | usage完全性 | 原裁定 |','| --- | ---: | ---: | ---: | --- | --- | --- |']
        for r in sorted((r for r in runs if r['condition']==c),key=lambda r:r['recorded_total_tokens'],reverse=True):
            score='欠測' if r['passed_ids'] is None else str(r['passed_ids']);rate='欠測' if r['pass_rate'] is None else f'{r["pass_rate"]:.1f}%'
            out.append(f'| {r["label"]} | {r["recorded_total_tokens"]:,} | {score} | {rate} | {r["evaluation_outcome"]} | {str(r["source_usage_complete"]).lower()} | {r["evaluation_validity"]} |')
        out+=['']
    out+=['## 独立Run bootstrap','', '通常−不整合。20,000回、seed 20260911。平均・中央値・10% trimmed meanごとに、条件内でRunを独立再抽出した95% percentile区間。trimmed meanは上下それぞれfloor(0.1 × n)件を除く定義で、30件なら各3件、28件・29件なら各2件を除く。','',
      '| 指標 | 統計量 | 差 | 2.5%点 | 97.5%点 |','| --- | --- | ---: | ---: | ---: |']
    metric={'recorded_total_tokens':'記録済み総トークン','pass_rate':'合格率（ポイント）','usage_requests':'usage応答回数','tokens_per_recorded_request':'Run内1応答当たりトークン'}
    stat={'mean':'平均','median':'中央値','trimmed_mean_10pct':'両端10%除外平均'}
    for r in stats['bootstrap']:out.append(f'| {metric[r["metric"]]} | {stat[r["statistic"]]} | {r["normal_minus_anti"]:,.3f} | {r["lower"]:,.3f} | {r["upper"]:,.3f} |')
    out+=['','## 全57 IDの合否','', '分母は通常28件・不整合29件。下記は合格率が得られたRunだけの件数。T-006-05は2ケース両方がpassのときだけ合格。failとblockedが混在する場合はfailをIDの状態とする。','',
      '| ID | 項目 | 通常 合格／fail／blocked | 不整合 合格／fail／blocked |','| --- | --- | ---: | ---: |']
    for r in stats['items']:
        title=r['title'].replace('🟢 ','').replace('🔴 ','').replace('🟡 ','')
        out.append(f'| {r["test_id"]} | {title} | {r["normal_passed"]} / {r["normal_fail"]} / {r["normal_blocked"]} | {r["anti_passed"]} / {r["anti_fail"]} / {r["anti_blocked"]} |')
    out+=['','## 追加の読み取り','',
      '機能別の集計は `data/features.csv`、得点帯と到達範囲は `data/score_bands.csv`、各種の除外感度は `data/sensitivity.csv`、相関は `data/correlations.csv`、終了理由とCLI終了コードはSQL Q12に保持した。終了コードと完成宣言は同一ではなく、製品品質の代わりには使わない。','',
      'usage完全性がtrueのRunだけに限定すると通常18件・不整合24件へ対象が変わる。この選別で記録量の差が変わっても、欠測分の補正や条件効果の推定にならないため、主集計には採用しない。','',
      '全群の総量を応答数で割ると通常65,612.47、不整合55,869.50トークン/応答。Run内の平均をさらにRun間で平均した値とは重みが異なる。対称的な算術分解では平均トークン差2,640,499.47のうち、応答回数に対応する項が1,360,598.13、1応答量に対応する項が1,279,901.33となる。これは恒等式による分解であり、因果寄与の推定ではない。','']
    (a.output/'supplement.md').write_text('\n'.join(out),encoding='utf-8')
    print({'claims':len(claims),'run_rows':len(runs),'item_rows':len(stats['items'])})
if __name__=='__main__':main()

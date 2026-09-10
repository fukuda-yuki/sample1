"""Create the tabular supplement from the frozen SQLite-derived results."""
from pathlib import Path
import argparse
import collections
import json

BASE=Path(__file__).resolve().parent
NAMES={'normal':'通常','anti':'不整合'}
BATCHES={'previous':'前回・直列','additional':'追加・並列','cumulative':'累計'}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def number(value,decimals=1):return '欠測' if value is None else f'{value:,.{decimals}f}'
def table(headers,rows):
    def cell(v):return str(v).replace('|','／').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                     *['| '+' | '.join(cell(v) for v in r)+' |' for r in rows]])

def main(data,output):
    d=read(data/'results.json');t=d['tables'];r=t['runs']
    component_rows=read(data/'sql-evidence.json')['queries']['C15_token_components_post_hoc']['rows']
    parts=['# 累計60予定枠の補足集計',
        '本文は[評価レポート](report.md)、完全な行データは[Run別CSV](data/runs.csv)と[分析SQLite](data/analysis.sqlite)にある。'
        '本補足は保存されたデータだけから生成する。Run名には前回／追加のバッチを付け、同じ番号を同一Runとして扱わない。'
        '「合格ID」は保存済みv6の出力であり、有効な製品品質の確定値ではない。評価不能の原出力に0があっても、分析欄は欠測とする。',
        '## 1. 予定枠と個別結果',
        table(['バッチ','Run','記録済み総トークン','合格ID／57','合格率（%）','評価出力','裁定'],[
            [BATCHES[x['batch']],x['planned_run'],number(x['recorded_total_tokens'],0),number(x['passed_ids'],0),
             number(x['recorded_pass_rate']),x['evaluation_outcome'] or '未取得',x['evaluation_validity'] or '未裁定'] for x in r]),
        '## 2. 条件別の分布',
        'トークンと合格IDでは欠測件数が異なる。標準偏差はRun間の標本標準偏差である。代替モデルがある場合はモデルごとの行を追加し、主比較と分ける。',
        table(['対象','モデル','条件','指標','有効件数','欠測','合計','平均','中央値','標準偏差','最小','最大'],[
            [BATCHES[s['stratum']],s['model'],NAMES[s['condition']],('トークン' if metric=='tokens' else '合格ID'),
             s[metric]['n'],s[metric]['missing'],*[number(s[metric][k],0 if k=='sum' else 2) for k in ('sum','mean','median','sd','min','max')]]
            for s in t['summaries'] if s['model']!='all' for metric in ('tokens','passed_ids')]),
        '## 3. 予定ペアと不確実性',
        '差の向きは不整合条件 − 通常条件。ペアは取得バッチ内の予定順ブロックであり、モデルの乱数を共有しない。'
        '不完全なペアは当該指標のペア推定だけから除き、個別Runや他の指標を消さない。',
        table(['対象','指標','完全ペア数','平均差','95%区間の下限','95%区間の上限'],[
            [BATCHES[x['stratum']],('記録済み総トークン' if x['metric']=='token_difference' else '合格率（ポイント）'),x['pairs'],
             *[number(x[k],2) for k in ('mean','lower','upper')]] for x in t['bootstrap']]),
        '20,000回、seed 20260911。前回と追加を別々に復元抽出し、累計では各バッチの完全ペア数を維持するpercentile bootstrap。'
        'この区間はモデル一般、アプリ一般、評価器の正しさに関する不確実性を含まない。',
        table(['バッチ','ペア','先行条件','トークン差','合格ID差','合格率差（ポイント）'],[
            [BATCHES[x['batch']],x['pair_id'],NAMES[x['first_condition']],number(x['token_difference'],0),number(x['passed_difference'],0),number(x['pass_rate_difference_pp'],2)] for x in t['pairs']]),
        '## 4. 取得順とペア除外の感度分析',
        '前半／後半は前回が予定ペア1〜5／6〜10、追加が1〜10／11〜20。並列取得で先行とは開始予約順を指し、完了順や同時負荷の割付ではない。',
        table(['対象','選択','予定ペア数','トークンの完全ペア数','合格率の完全ペア数','平均トークン差','平均合格率差（ポイント）'],[
            [BATCHES[x['stratum']],x['selection'],x['pairs'],x['token_pairs'],x['score_pairs'],number(x['token_difference'],0),number(x['pass_rate_difference_pp'],2)] for x in t['sensitivity']]),
        '累計の1ペアずつの除外結果は[leave_one_pair_out.csv](data/leave_one_pair_out.csv)に全30通りを保存する。'
        '外れ値を主集計から取り除く操作ではなく、特定ペアへの依存度を点検する補助分析である。',
        '## 5. トークン、応答回数、合格IDの関係',
        table(['対象','条件','両指標の件数','Pearson相関','Spearman順位相関'],[
            [BATCHES[x['stratum']],NAMES.get(x['condition'],'両条件'),x['n'],number(x['pearson'],3),number(x['spearman'],3)] for x in t['correlations']]),
        '両条件を混ぜた相関は条件構成を含む。条件内相関も投入量の無作為割付ではなく、試行錯誤や実装の難しさなどの交絡を含む。',
        table(['対象','条件','件数','HTTP 200応答数','応答数／Run','記録済みトークン／応答'],[
            [BATCHES[x['stratum']],NAMES[c],x[c]['n'],x[c]['responses'],number(x[c]['responses_per_run'],2),number(x[c]['tokens_per_response'],2)]
            for x in t['response_decomposition'] for c in ('normal','anti')]),
        'HTTP 200はgatewayが記録した応答の単位であり、モデル内の思考段階や有用な処理回数ではない。'
        '平均トークン差（通常 − 不整合）は、平均応答回数の差×両条件の平均応答サイズと、平均応答サイズの差×両条件の平均応答回数の対称分解として示す。'
        'これは恒等的な会計分解であり、原因の寄与率ではない。',
        table(['対象','応答回数の差の成分','応答サイズの差の成分'],[
            [BATCHES[x['stratum']],number(x['count_component'],0),number(x['size_component'],0)] for x in t['response_decomposition']]),
        '大消費Runの確認を契機に、保存済みusageの入力・出力・キャッシュの内訳を事後集計した。キャッシュ済み入力は入力の内数であり、別に加算しない。入力＋出力と元の記録済み総トークンが一致することを全Runで照合する。料金への換算は行わない。',
        table(['バッチ','条件','内訳取得Run数','入力トークン','出力トークン','キャッシュ済み入力','キャッシュ明細が揃うRun数'],[
            [BATCHES[x['batch']],NAMES[x['condition']],x['observed_runs'],number(x['input_tokens'],0),number(x['output_tokens'],0),number(x['cached_input_tokens'],0),x['complete_cache_detail_runs']] for x in component_rows]),
        '## 6. 終了理由と評価到達範囲',
        '実装役の完了宣言、CLIの終了コード、監督側の強制停止理由は異なる記録である。'
        '下表は原本に記録された終了理由で集計し、詳細な組合せは[SQL C07](data/sql-evidence.json)とRun別CSVで示す。',
        table(['対象','条件','原本の終了理由','件数','平均トークン','平均合格ID'],[
            [BATCHES[x['stratum']],NAMES[x['condition']],x['reason'],x['n'],number(x['token_mean'],0),number(x['passed_mean'],2)] for x in t['terminations']]),
        table(['対象','条件','業務判定到達（合計）','前提条件で未到達（合計）','評価未確定（合計）','到達情報なし（合計）'],[
            [BATCHES[x['stratum']],NAMES[x['condition']],*[number(x[k]['sum'],0) for k in ('business_assertion_reached','prerequisite_blocked','evaluation_unresolved','reachability_unknown')]] for x in t['reachability']]),
        '到達と評価未確定は重なる場合があり、これらの列を合計して58ケースに戻すことはできない。'
        '機能ごとの到達記録は[feature_runs.csv](data/feature_runs.csv)、全ケースの保存状態は[case_results.csv](data/case_results.csv)にある。',
        '## 7. 外れ値と反例の追跡',
        '当該バッチ・条件内の四分位範囲（IQR）の1.5倍を超えた値を機械的に列挙する。累計にも同じ規則を適用するため、同じRunが複数回現れる。いずれも主集計から除外しない。',
        table(['対象','条件','指標','Run','値','下限','上限'],[
            [BATCHES[x['stratum']],NAMES[x['condition']],('トークン' if x['metric']=='recorded_total_tokens' else '合格ID'),x['slot_key'],number(x['value'],0),number(x['lower'],2),number(x['upper'],2)] for x in t['outliers']]),
        '## 8. 原本と証拠の対応',
        'Run UUID、評価UUID、提出hash、v6のhashは[分析SQLite](data/analysis.sqlite)と[private-evidence-index.json](source/additional/private-evidence-index.json)で照合できる。'
        '非公開の画面・trace・評価コード本体は公開フォルダへ含めず、独立保管庫の参照とhashを残す。'
        '追加40件の固定コード・可視文書の読解は[qualitative-review.json](reviews/qualitative-review.json)、前回20件から引き継いだ読解記録は[previous/qualitative.json](source/previous/qualitative.json)、選択した画面・通信記録の確認は[evaluation-observations.json](reviews/evaluation-observations.json)を参照する。'
        '後者の部分的な動作記録を、全Runの全操作経路の検証へ拡張しない。',
        '再生成は `python build_supplement.py`。取得や評価は実行せず、[再集計・再採点手順](reproduce.md)に従って保存済みデータだけを使う。']
    output.write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    print(json.dumps({'planned_rows':len(r),'sections':8,'model_calls':0,'evaluations':0}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=BASE/'data');parser.add_argument('--output',type=Path,default=BASE/'supplement.md')
    args=parser.parse_args();main(args.data,args.output)

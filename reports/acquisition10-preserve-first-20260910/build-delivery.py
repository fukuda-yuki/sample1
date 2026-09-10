"""Publish a data-acquisition readout from validated, explicitly selected exports."""
import sys,csv,json,shutil,statistics,collections,hashlib
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from copilot_batch import export
from preserve import read,digest,write_new
base=root/'results/acquisition10-resume-20260910';old=root/'results/acquisition10-20260910';batch=old/'batch'
private=root.parent/'sample1-private-eval-linux/acquisition10-20260910/validity.json'
index=read(batch/'run-index.json');started=[r for r in index['runs'] if r['run_id']]
assert not any(r['status'] in ('running','reserved','recovery_required') for r in started)
provenance=export(batch,private)
source=batch/read(batch/'export-current.json')['directory']
out=root/'reports/acquisition10-preserve-first-20260910';out.mkdir(parents=True,exist_ok=False)
(out/'.gitattributes').write_text('* -text\n',encoding='utf-8')
for p in source.iterdir():
 if p.is_file() and p.suffix in ('.csv','.json','.jsonl','.sqlite','.png'):
  shutil.copy2(p,out/('export-complete.json' if p.name=='complete.json' else p.name))
rows=list(csv.DictReader((source/'runs.csv').open(encoding='utf-8-sig')))
with (source/'analysis.sqlite').open('rb') as f: assert f.read(16)==b'SQLite format 3\x00'
typed=[]
for row in rows:
 converted={}
 for key,value in row.items():
  if value=='':value=None
  elif value in ('True','False'):value=value=='True'
  elif key in ('total_tokens','observed_tokens','input_tokens','output_tokens','passed','failed','blocked','errors','denominator'):value=int(value)
  elif key=='quality_percent':value=float(value)
  elif key.endswith('_json'):
   try:value=json.loads(value)
   except ValueError:pass
  converted[key]=value
 typed.append(converted)
write_new(out/'runs.json',typed)
coverage_summary=[]
for condition in ('normal','anti'):
 group=[r for r in typed if r['run_id'] and r['condition']==condition and r['evaluation_completed']]
 coverage=[r.get('coverage_json') or {} for r in group]
 causes=collections.Counter();responsibilities=collections.Counter()
 for c in coverage:causes.update(c.get('causes',{}));responsibilities.update(c.get('responsibilities',{}))
 coverage_summary.append(dict(condition=condition,evaluated_runs=len(group),required_cases=sum(c.get('required_cases',0) for c in coverage),
  business_assertion_reached=sum(f.get('business_assertion_reached',0) for c in coverage for f in c.get('features',{}).values()),
  prerequisite_blocked=sum(f.get('prerequisite_blocked',0) for c in coverage for f in c.get('features',{}).values()),
  raw_causes=dict(causes),adjudicated_responsibilities=dict(responsibilities)))
write_new(out/'evaluation-coverage.json',coverage_summary)
safe_cases=[json.loads(line) for line in (out/'test-results.jsonl').read_text().splitlines() if line.strip()]
ledger=read(root/'evaluation/requirements-ledger.json')
ap_items=[item for item in ledger['items'] if item['ap001_relation'].startswith(('直接：','前提経路に影響しうる'))]
assert len(ap_items)==7
ap_diagnostics=[]
for item in ap_items:
 for condition in ('normal','anti'):
  run_ids={r['run_id'] for r in typed if r['condition']==condition and r['evaluation_completed']}
  cases=[c for c in safe_cases if c['run_id'] in run_ids and c['evaluation_id']==item['evaluation_id']]
  counts=collections.Counter(c['status'] for c in cases)
  assert len(cases)==len(run_ids)*item['scoring_unit']['required_subcases']
  ap_diagnostics.append(dict(evaluation_id=item['evaluation_id'],condition=condition,
   ap001_relation=item['ap001_relation'],evaluated_runs=len(run_ids),raw_cases=len(cases),
   counts={status:counts[status] for status in ('pass','fail','blocked','error')}))
write_new(out/'ap001-raw-diagnostics.json',dict(ledger_sha256=digest(root/'evaluation/requirements-ledger.json'),
 scope='Predefined AP-001-related cases; diagnostic raw status counts, not an additional quality score.',rows=ap_diagnostics))
model_counts=collections.Counter(r['model_id'] for r in typed if r['run_id'])
condition_counts={}
retention=[]
for condition in ('normal','anti'):
 group=[r for r in index['runs'] if r['condition']==condition]
 completed=[]
 for row in group:
  if not row['run_id']:continue
  run=batch/'runs'/row['planned_run']/'attempt';m=read(run/'manifest.json')
  assert m['processes_stopped'] and m['submission_fixed']
  receipt=read(run.parent/'acquisition-completion.json')
  completed.append(m['end_reason'])
  http=collections.Counter(str(json.loads(line).get('http_status')) for line in (run/'raw-usage/events.jsonl').read_text().splitlines() if line.strip()) if (run/'raw-usage/events.jsonl').exists() else collections.Counter()
  retention.append(dict(planned_run=row['planned_run'],run_id=row['run_id'],submission_hash=digest(run/'snapshot.json'),
    original=read(run/'preservation.json'),original_restoration=receipt['original_restoration'],linked_restoration=receipt['linked_restoration'],
    processing=read(run/'measurement-ref.json') if (run/'measurement-ref.json').exists() else None,
    lockfiles={name:value for name,value in read(run/'snapshot.json').items() if Path(name).name in ('package-lock.json','npm-shrinkwrap.json','yarn.lock','pnpm-lock.yaml','bun.lock','bun.lockb','packages.lock.json','poetry.lock','uv.lock','Cargo.lock','go.sum')},
    management_sha256=m['management']['files'],elapsed_seconds=m['elapsed_seconds'],started_at=m['started_at'],ended_at=m['ended_at'],
    completion_declaration_captured=bool(m.get('completion_declaration') or (run.parent/'completion-intervention.json').exists()),
    raw_end_reason=m['end_reason'],exit_code=m['exit_code'],stop_trigger=m.get('stop_trigger'),gateway_http=dict(http),response_spool_files=len(list((run/'raw-usage/responses').glob('*.sse')))))
 condition_counts[condition]=dict(planned=10,started=len(completed),collected=len(completed),
    normal_runner_completion=completed.count('agent_completed'),other_ended=len(completed)-completed.count('agent_completed'),not_started=10-len(completed))
measurement_profile=[]
for condition in ('normal','anti'):
 group=[r for r in typed if r['run_id'] and r['condition']==condition]
 retained=[r for r in retention if r['planned_run'].startswith(condition+'-')]
 http=collections.Counter()
 for r in retained:http.update(r['gateway_http'])
 measurement_profile.append(dict(condition=condition,n=len(group),total_missing=sum(r['total_tokens'] is None for r in group),
  native_unverified=sum(r.get('native_calls_verified') is not True for r in group),
  trace_incomplete=sum(r.get('trace_structure_complete') is False for r in group),
  http=dict(http),runs_with_http_400=sum(r['gateway_http'].get('400',0)>0 for r in retained)))
write_new(out/'measurement-profile.json',measurement_profile)
stats=[]
for model in sorted(model_counts):
 for condition in ('normal','anti'):
  subset=[r for r in typed if r['run_id'] and r['model_id']==model and r['condition']==condition]
  values=[r['total_tokens'] for r in subset if r['total_tokens'] is not None]
  quality=[r['quality_percent'] for r in subset if r['quality_percent'] is not None]
  raw=[100*r['passed']/r['denominator'] for r in subset if r['evaluation_completed'] and r['passed'] is not None and r['denominator']]
  observed=[r['observed_tokens'] for r in subset if r['observed_tokens'] is not None]
  stats.append(dict(model=model,condition=condition,n=len(subset),token_n=len(values),
    token_mean=statistics.mean(values) if values else None,token_median=statistics.median(values) if values else None,
    token_min=min(values) if values else None,token_max=max(values) if values else None,
    observed_token_n=len(observed),observed_token_mean=statistics.mean(observed) if observed else None,
    observed_token_median=statistics.median(observed) if observed else None,
    raw_n=len(raw),raw_pass_mean_percent=statistics.mean(raw) if raw else None,
    raw_pass_median_percent=statistics.median(raw) if raw else None,raw_pass_min_percent=min(raw) if raw else None,
    raw_pass_max_percent=max(raw) if raw else None,
    quality_n=len(quality),quality_mean=statistics.mean(quality) if quality else None,quality_median=statistics.median(quality) if quality else None))
primary={s['condition']:s for s in stats if s['model']=='muse-spark-1.2-contributor'}
differences={}
for key in ('token_mean','token_median','observed_token_mean','observed_token_median','raw_pass_mean_percent','raw_pass_median_percent','quality_mean','quality_median'):
 n=primary.get('normal',{}).get(key);a=primary.get('anti',{}).get(key);differences[key]=None if n is None or a is None else a-n
by_slot={r['planned_run']:r for r in typed};paired=[]
for block in range(1,11):
 group={r['condition']:by_slot[r['planned_run']] for r in index['runs'] if r['block']==block}
 n=group['normal'];a=group['anti']
 same_primary=all(r['run_id'] and r['model_id']=='muse-spark-1.2-contributor' for r in (n,a))
 pair=dict(block=block,normal_run_id=n['run_id'],anti_run_id=a['run_id'],both_primary=same_primary)
 for key in ('total_tokens','quality_percent'):
  pair[key+'_anti_minus_normal']=a[key]-n[key] if same_primary and a[key] is not None and n[key] is not None else None
 raw_pair=same_primary and all(r['evaluation_completed'] and r['passed'] is not None and r['denominator'] for r in (n,a))
 pair['raw_v6_percent_anti_minus_normal']=100*a['passed']/a['denominator']-100*n['passed']/n['denominator'] if raw_pair else None
 paired.append(pair)
paired_stats={}
for key in ('total_tokens_anti_minus_normal','quality_percent_anti_minus_normal','raw_v6_percent_anti_minus_normal'):
 values=[p[key] for p in paired if p[key] is not None]
 paired_stats[key]=dict(n=len(values),mean=statistics.mean(values) if values else None,median=statistics.median(values) if values else None)
write_new(out/'paired-runs.json',paired)
token_pair_values=[p['total_tokens_anti_minus_normal'] for p in paired if p['total_tokens_anti_minus_normal'] is not None]
token_pair_directions=dict(anti_lower=sum(v<0 for v in token_pair_values),equal=sum(v==0 for v in token_pair_values),anti_higher=sum(v>0 for v in token_pair_values),missing_pairs=10-len(token_pair_values))
summary=dict(experiment_id=index['experiment_id'],acquisition_complete=len(retention)==20,planned=20,started=len(started),collected=len(retention),
 not_started=20-len(started),condition_counts=condition_counts,model_counts=dict(model_counts),statistics=stats,
 primary_anti_minus_normal=differences,processing_policy='preserve-first-v2',quality_status='See per-Run validity; no missing value is zero',
 paired_primary_differences=paired_stats,
 paired_token_directions=token_pair_directions,
 evaluation_completed=provenance['evaluation_completed'],evaluation_valid=provenance['evaluation_valid'],
 observed_token_sum=sum(r['observed_tokens'] or 0 for r in typed if r['run_id']),
 confirmed_token_sum=sum(r['total_tokens'] or 0 for r in typed if r['run_id']),
 missing_totals=sum(r['run_id'] is not None and r['total_tokens'] is None for r in typed),
 submissions_without_recognized_lockfile=sum(not r['lockfiles'] for r in retention),
 validity_counts=dict(collections.Counter(r['evaluation_validity'] for r in typed if r['run_id'])))
write_new(out/'summary.json',summary);write_new(out/'retention.json',dict(runs=retention,readiness=read(base/'ready.json')))
shutil.copy2(batch/'planned-runs.json',out/'planned-runs.json')
def fmt(n):return '未確定' if n is None else f'{n:,.1f}'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',*['| '+' | '.join(str(x) for x in row)+' |' for row in rows]])
def model_label(model):return {'muse-spark-1.2-contributor':'Muse 1.2','muse-spark-1.3-contributor':'Muse 1.3','omen-alpha':'Omen Alpha','mimo-v2.5':'MiMo V2.5'}.get(model,model)
metric_labels={'token_mean':'総tokenの平均差','token_median':'総tokenの中央値差','observed_token_mean':'観測下限の平均差','observed_token_median':'観測下限の中央値差','raw_pass_mean_percent':'raw v6平均差（ポイント）','raw_pass_median_percent':'raw v6中央値差（ポイント）','quality_mean':'有効品質の平均差（ポイント）','quality_median':'有効品質の中央値差（ポイント）'}
pair_labels={'total_tokens_anti_minus_normal':'総token','quality_percent_anti_minus_normal':'有効品質（ポイント）','raw_v6_percent_anti_minus_normal':'raw v6 pass率（ポイント）'}
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
import platform,sqlite3
write_new(out/'analysis-runtime.json',dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,
 matplotlib=matplotlib.__version__,platform=platform.platform(),python_executable=sys.executable,
 source_commit=__import__('subprocess').check_output(['git','rev-parse','HEAD'],text=True).strip(),
 scope='Runtime used for export and report generation; evaluation Docker image and per-Run environment are separately pinned.'))
from render_delivery_plots import render
render(out,typed)
report=['# 原本保持を優先したnormal/antiデータ取得','',
 f'予定20開始に対し、開始{len(started)}件、回収・保全{len(retention)}件、未開始{20-len(started)}件です。既存anti 1件を保持し、同じ予定表で残枠を実行しました。失敗や測定欠損を理由とする取り直し・削除はありません。','',
 '最初のantiも原本を変更せず再利用し、保存済みgateway記録から7,168,678 tokensを照合しました。旧usageのnull値と親span欠落の記録を残し、選択した新処理の結果を追加しています。','',
 '## 取得と検証の状態','',
 'seed 20260910で固定した10ペアの予定順を用い、各Runは新規セッション・隔離環境、上限60分、effort未指定、実装子エージェントなしで実行しました。同時実装数は1です。配布入力は自条件specと共通契約のみ。AP-001、57評価ID・58ケース・等配点を維持しています。','',
 table(['条件','予定','開始','回収','通常終了','その他終了','未開始'],[[k,v['planned'],v['started'],v['collected'],v['normal_runner_completion'],v['other_ended'],v['not_started']] for k,v in condition_counts.items()]),'',
 '通常終了はrunnerのagent_completed。最初のantiは完了宣言後の管理停止でraw agent_error/137を保持しています。再開後に完了宣言を検出して管理停止したRunは、実際の終了コードと停止理由・宣言の記録を分けました。取得完了は有効採点の完了を意味しません。','',
 table(['モデル','開始件数'],[[k,v] for k,v in model_counts.items()]),'',
 f"評価実行終了は{provenance['evaluation_completed']}件、有効品質が確定した評価は{provenance['evaluation_valid']}件です。既存antiのv6 raw 32/57、invalid裁定を保持しました。未採点・未確定の提出物もすべて保存され、同一提出hashで評価器を更新できます。",'',
 f"1.2の確定token平均はnormal {fmt(primary['normal']['token_mean'])}（n={primary['normal']['token_n']}）、anti {fmt(primary['anti']['token_mean'])}（n={primary['anti']['token_n']}）でした。raw v6 pass率の平均差はanti − normalで{fmt(differences['raw_pass_mean_percent'])}ポイントです。tokenの欠測件数が条件間で異なり、評価妥当性も未確定のため、この数値だけで効率や品質の優劣は判断しません。",'',
 '全実装の停止後、再開分19件の初回v6評価を独立したアプリ・DB・評価コンテナで最大4件ずつ実行しました。評価中の実装エージェント数は0です。評価の実行順・UUID・準備記録も保持し、実装の直列条件と評価の実行条件を分けて記録しています。','',
 '## 条件別の記述統計','',
 '単位は1 Runです。総token確定値はgatewayで開始・終端・usageが揃ったRunのみ。有効品質は妥当と裁定した評価の57 ID等配点です。未確定Runは分母へ混ぜず、各指標のnを併記します。原本を保存している件数とは異なります。','',
 table(['モデル','条件','開始n','総token確定n','平均','中央値','最小','最大'],[[model_label(s['model']),s['condition'],s['n'],s['token_n'],fmt(s['token_mean']),fmt(s['token_median']),fmt(s['token_min']),fmt(s['token_max'])] for s in stats]),'',
 table(['1.2のanti − normal','差'],[[metric_labels[k],fmt(v)] for k,v in differences.items()]),'',
 table(['同じ予定ペア内のanti − normal','対応が揃うペアn','差の平均','差の中央値'],[[pair_labels[k],v['n'],fmt(v['mean']),fmt(v['median'])] for k,v in paired_stats.items()]),'',
 f"総tokenが双方で確定した{len(token_pair_values)}ペアでは、antiが少ないペアが{token_pair_directions['anti_lower']}、同量が{token_pair_directions['equal']}、多いペアが{token_pair_directions['anti_higher']}でした。残る{token_pair_directions['missing_pairs']}ペアには欠測があり、有効品質も未確定です。この観測を品質を維持した効率改善とは解釈できません。",'',
 'ペア内比較も両方が1.2で、対象指標が観測できたペアだけです。raw v6の差は未裁定の評価器出力差です。10ペア以下の探索データとして記述し、欠測や評価制約が残る段階で有意差・優劣を主張しません。','',
 '![Run別総トークン分布](token-distribution.png)','',
 f"総tokenが未確定のRunは{summary['missing_totals']}件あります。確定値だけの平均・中央値は欠測の影響を受けるため、全Runの条件差として扱えません。観測できたtokenの合計は{summary['observed_token_sum']:,}で、欠測がある場合は総消費の下限です。",'',
 table(['モデル','条件','観測token n','観測下限の平均','観測下限の中央値'],[[model_label(s['model']),s['condition'],s['observed_token_n'],fmt(s['observed_token_mean']),fmt(s['observed_token_median'])] for s in stats]),'',
 '観測下限同士の差は、真の総消費量の条件差に対する上限・下限にはなりません。条件ごとの欠測件数と併せ、保存済み観測値の記述統計として扱います。','',
 table(['モデル','条件','有効品質n','品質平均%','品質中央値%'],[[model_label(s['model']),s['condition'],s['quality_n'],fmt(s['quality_mean']),fmt(s['quality_median'])] for s in stats]),'',
 '![総トークンと有効品質](tokens-quality.png)','',
 '総トークンは実装gatewayの開始・終端・usageを照合したinput+outputで、研究管理・採点の計算量は対象外です。native call対応、親span構造、monitor状態は独立項目です。キャッシュ入力・reasoningを二重加算しません。欠測はnullと観測下限を残します。有効品質が未確定なら散布図の点を描きません。','',
 '今回のmonitor照合は、専用DBへのrawデータの取込と読戻しです。通常のMonitor UIや派生trace表示の受入検証までを測定範囲に含めていません。専用DBの整合したsnapshotも非公開の管理証拠として保管しています。','',
 table(['条件','Run n','総token欠測Run','native未確認Run','親span不完全Run','400発生Run','HTTP 400応答数'],[[s['condition'],s['n'],s['total_missing'],s['native_unverified'],s['trace_incomplete'],s['runs_with_http_400'],s['http'].get('400',0)] for s in measurement_profile]),'',
 '上流400を含むRunでも取得・保存は続けました。エラー応答にusageがない場合、総量の完全性は未確定です。Run数とHTTP応答数を分け、欠測を除いた比較の偏りを残る制約として扱います。詳細は[measurement-profile.json](measurement-profile.json)とIssue #47にあります。','',
 '## v6のraw結果と評価範囲','',
 table(['モデル','条件','raw結果n','raw pass率平均%','中央値%','最小%','最大%'],[[model_label(s['model']),s['condition'],s['raw_n'],fmt(s['raw_pass_mean_percent']),fmt(s['raw_pass_median_percent']),fmt(s['raw_pass_min_percent']),fmt(s['raw_pass_max_percent'])] for s in stats]),'',
 '![総トークンと未裁定のraw結果](tokens-raw-v6.png)','',
 'raw pass率は初回v6が返したpass ID数/57です。評価器の操作制約・前提未成立・未到達も含むため、製品品質とは区別します。raw差をnormal/antiの品質差と解釈せず、通常UIの証拠と再採点を使って検証するための基準記録として保持します。ケース別raw状態・到達範囲・既存裁定はCSVのcoverage_jsonとSQLiteにあります。','',
 table(['条件','評価終了Run','要求ケース','業務判定へ到達','前提未成立でblocked'],[[s['condition'],s['evaluated_runs'],s['required_cases'],s['business_assertion_reached'],s['prerequisite_blocked']] for s in coverage_summary]),'',
 '以下はケース単位の原因分類です。原因裁定のないraw passケース（none）は表から省いています。未裁定の非passケースは「原因未確定」に含めます。','',
 table(['条件','裁定済み実装原因','評価器原因','評価環境原因','指示の曖昧さ','原因未確定'],[[s['condition'],*[s['adjudicated_responsibilities'].get(k,0) for k in ('implementation','evaluator','evaluation_environment','instruction_ambiguity','unconfirmed')]] for s in coverage_summary]),'',
 '到達数は保存済みケース記録に基づきます。評価側原因の裁定は通常UI等で確認した範囲に限定し、未裁定を実装失敗へ振り替えません。詳しい分類は[evaluation-coverage.json](evaluation-coverage.json)に保持しています。','',
 '準備記録の要約は[evaluation-preparation.json](evaluation-preparation.json)です。resetとUIログインによるseed観測の件数をRunごとに残しています。準備記録だけで採点妥当性を認定してはいません。','',
 'AP-001との直接関係が台帳に定義されたT-006群と、前提経路への影響が記載されたT-010-01を次に示します。各セルはケース単位のpass / fail / blocked / error件数です。T-006-05は各Runに2ケースあるため、他の行とはケース数が異なります。追加の品質点や分母としては使いません。','',
 table(['評価ID','normal: P / F / B / E','anti: P / F / B / E'],[[item['evaluation_id'],*[' / '.join(str(next(d for d in ap_diagnostics if d['evaluation_id']==item['evaluation_id'] and d['condition']==condition)['counts'][status]) for status in ('pass','fail','blocked','error')) for condition in ('normal','anti')]] for item in ap_items]),'',
 'blockedは前提未成立のraw状態で、すべての未到達を表すわけではありません。画面探索中の失敗などはfailにも含まれます。項目別集計は[ap001-raw-diagnostics.json](ap001-raw-diagnostics.json)、Run別の状態は[test-results.jsonl](test-results.jsonl)から追跡できます。','',
 'T-006-01とT-006-03は、normalが各10件pass、antiが各0件pass（8 fail・2 blocked）でした。これは閾値の解釈を再確認する対象です。一方、業務判定への到達はnormal 486/580、anti 352/580で異なります。anti全体の低いraw値をAP-001だけの効果や一般的な実装不具合へ帰属させることはできません。','',
 '確認済みの実装原因として、normal-002のT-002-02ではログアウトPOSTが200で成功した後も指定メッセージが表示されませんでした。固定ソースでは、遷移先で表示に必要なstate/queryを呼出側が渡していません。同じIDでも、初回antiのログインリンク探索の問題とは原因が異なります。この1項目の裁定で、他のログアウト要件や総合品質まで認定してはいません。画面・trace・ソースhashを結び付けた裁定を追加し、raw 50/57は保持しています。','',
 '## 保存・再利用','',
 table(['Run枠','総token確定値','観測token','raw pass / 57','終了理由（raw）','評価妥当性'],[[r['planned_run'],'欠測' if r['total_tokens'] is None else f"{r['total_tokens']:,}",'欠測' if r['observed_tokens'] is None else f"{r['observed_tokens']:,}",'未評価' if not r['evaluation_completed'] else f"{r['passed']} / 57",r['end_reason'],r['evaluation_validity']] for r in typed]),'',
 '[Run CSV](runs.csv)、[Run JSON](runs.json)、[SQLite](analysis.sqlite)、[統計JSON](summary.json)、[保全参照](retention.json)、[固定予定順](planned-runs.json)に対応を収録しています。独立保管庫はC:\\Users\\mwam0\\ResearchArchives\\sample1です。非公開評価器・画面・traceは公開Gitに含めません。','',
 '[集計確認Notebook](analysis-checks.ipynb)は同じフォルダのJSON・SQLiteだけで件数・参照関係・統計を再確認します。実行結果は[notebook-verification.json](notebook-verification.json)、レポートと管理証拠の独立保管・復元参照は[delivery-preservation.json](delivery-preservation.json)です。','',
 '各Runの入力、設定、CLI/image/管理版、開始終了、固定ソース・lockfile・hash、CLI応答、gateway usage、native telemetry、monitor照合を保持しています。評価時のコンテナ設定とテスト用メール出力も非公開の最終保管物に含めました。再開後はgateway応答ストリームも秘密情報を除いて保存しました。初回antiにはこの追加ストリーム保存がなく、取得済みCLI応答・usage・telemetryを保持しています。取得していない情報は後から捏造しません。','',
 f"提出物に含まれる既知のlockfile名とhashもretention.jsonに収録しました。該当lockfileが確認できない提出物は{summary['submissions_without_recognized_lockfile']}件です。lockfileがない場合も提出物を保持し、その不足を再評価環境の再構成時に考慮します。",'',
 '## 解釈と残る作業','',
 '主比較はMuse Spark 1.2同士に限定し、代替モデルを混ぜません。各条件最大10開始、単一アプリ・AP-001の探索結果です。取得時期、初回と再開後の管理停止処理の差、provider障害、欠測を記録し、条件差を一般的な因果効果と断定しません。57 ID・58ケース・等配点は維持します。','',
 '計測器・評価器の不具合を修正した場合は、旧raw・処理・裁定を保持して新処理UUID/評価UUIDと明示的選択を追加します。生成物は変更せず、実装役への評価結果の返却もしません。必要な後処理と原本の復元・再集計証拠は[verification.json](verification.json)、手順は[再処理手順](reproduce.md)を参照してください。','']
(out/'report.md').write_text('\n'.join(report),encoding='utf-8')
shutil.copy2(base/'reproduce-draft.md',out/'reproduce.md')
shutil.copy2(base/'report-source-notes.md',out/'source-notes.md')
shutil.copy2(Path(__file__),out/'build-delivery.py')
shutil.copy2(base/'render_delivery_plots.py',out/'render_delivery_plots.py')
print(json.dumps(summary,ensure_ascii=False))

"""Six Japanese research figures from frozen derived data, without model/runtime calls."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import LogLocator,FuncFormatter,NullLocator
import numpy as np

BASE=Path(__file__).resolve().parent
COLORS={'normal':'#26648E','anti':'#A45C15'}
NAMES={'normal':'通常条件','anti':'不整合条件'}
BATCHES={'previous':'前回・直列','additional':'追加・並列','cumulative':'累計'}
INK,GREY='#243746','#596773'
MODEL='muse-spark-1.2-contributor'

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def configure():
    choices=([Path(os.environ['REPORT_FONT'])] if os.environ.get('REPORT_FONT') else [])+[Path('/mnt/c/Windows/Fonts/YuGothR.ttc'),Path('C:/Windows/Fonts/YuGothR.ttc')]
    font=next((p for p in choices if p.exists()),None)
    if font is None:raise FileNotFoundError('Yu Gothic is required for Japanese figures')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(font)).get_name(),
        'font.size':12,'axes.titlesize':15,'axes.labelsize':13,'text.color':INK,'axes.labelcolor':INK,
        'xtick.color':INK,'ytick.color':INK,'axes.spines.top':False,'axes.spines.right':False,
        'axes.edgecolor':'#A6B2BA','figure.facecolor':'white','savefig.facecolor':'white',
        'axes.unicode_minus':False,'grid.color':'#DFE6EB','svg.fonttype':'path','svg.hashsalt':'sample1-cumulative-60-v1'})
    return font
def header(fig,number,title,subtitle):
    fig.text(.045,.955,f'図{number}  {title}',fontsize=18,weight='bold',va='top')
    fig.text(.045,.898,subtitle,fontsize=11.5,color=GREY,va='top')
def box(ax,x,y,w,h,text,color=COLORS['normal'],fill='#EDF4F8',size=12):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.009,rounding_size=0.013',
                              linewidth=1.4,edgecolor=color,facecolor=fill))
    ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,linespacing=1.55)
def arrow(ax,start,end):ax.annotate('',xy=end,xytext=start,arrowprops={'arrowstyle':'->','lw':1.6,'color':GREY})

def build(data_path,output):
    if output.resolve()==(BASE/'source').resolve() or (BASE/'source').resolve() in output.resolve().parents:
        raise ValueError('Cannot overwrite frozen source')
    output.mkdir(parents=True,exist_ok=True);font=configure();data=read(data_path)
    tables=data['tables'];runs=tables['runs'];pairs=tables['pairs'];primary=[r for r in runs if r['model_id']==MODEL]
    trace=[]
    def emit(fig,name,inputs,limits):
        fig.savefig(output/(name+'.png'),dpi=170,metadata={'Software':'Matplotlib'})
        fig.savefig(output/(name+'.svg'),metadata={'Date':None,'Creator':'Matplotlib'})
        trace.append({'figure':name,'source_data':inputs,'limitations':limits,
            'results_sha256':sha(data_path),'generator_sha256':sha(Path(__file__))})
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,9.2));header(fig,1,'独立した実装と、保存提出物の共通評価','前回・追加ともに両条件を実施。業務資料は各Runの自条件仕様書のみ')
    ax.set_position([.04,.035,.92,.80]);ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
    box(ax,.015,.83,.43,.13,'通常条件（normal）\n共通100万円・詳細100万円')
    box(ax,.555,.83,.43,.13,'不整合条件（anti）\n共通100万円・詳細50万円',COLORS['anti'],'#FAF1E6')
    box(ax,.20,.64,.60,.12,'両条件を各バッチに配置：同じモデル・CLI・実行image\n共通指示は矛盾の解釈と理由の記録、各Runは60分以内',GREY,'#F1F3F5',11.5)
    arrow(ax,(.23,.82),(.37,.77));arrow(ax,(.77,.82),(.63,.77))
    box(ax,.02,.43,.42,.14,'前回20開始：各条件10件\n実装は直列\n保存済み提出物を引き継ぐ')
    box(ax,.56,.43,.42,.14,'追加40開始を上限：各条件20件\n実装は最大5並列、空き枠を順次補充\n停止・固定・独立保管・復元後に補充',size=11.5)
    arrow(ax,(.36,.63),(.23,.58));arrow(ax,(.64,.63),(.77,.58))
    box(ax,.02,.23,.42,.13,'前回の保存済みv6評価を引き継ぐ\n再採点せず、旧裁定を維持')
    box(ax,.56,.23,.42,.13,'追加分を順次v6評価\n取得中は最大1件、取得終了後は最大4件')
    arrow(ax,(.23,.42),(.23,.37));arrow(ax,(.77,.42),(.77,.37))
    box(ax,.20,.02,.60,.13,'累計60予定枠を分析：前回／追加／累計を併記\n共通v6：100万円基準、57評価ID・58ケース\n記録済み合格率と有効品質を区別し、欠測を維持',GREY,'#F1F3F5',11.5)
    arrow(ax,(.23,.22),(.36,.16));arrow(ax,(.77,.22),(.64,.16))
    emit(fig,'01-study-flow',['analysis-policy.json','source/additional/planned-runs.json'],['前回20件の再実装・再採点は行っていない。'])

    log_tokens=all(r['recorded_total_tokens']>0 for r in primary if r['recorded_total_tokens'] is not None)
    subtitle='点は個別Run、太線は中央値。'+('トークンの縦軸は対数目盛。' if log_tokens else '')+'累計は同じRunの再表示'
    fig,axes=plt.subplots(1,2,figsize=(12,7.2));header(fig,2,'バッチと条件ごとの分布',subtitle)
    fig.subplots_adjust(left=.08,right=.97,top=.79,bottom=.20,wspace=.26)
    for ax,key,ylabel,scale in [(axes[0],'recorded_total_tokens','記録済み総トークン（百万）',1e6),(axes[1],'recorded_pass_rate','保存済みv6の合格率（%）',1)]:
        for b,batch in enumerate(BATCHES):
            for k,c in enumerate(NAMES):
                rows=[r for r in primary if r['condition']==c and (batch=='cumulative' or r['batch']==batch) and r[key] is not None]
                values=np.array([r[key]/scale for r in rows]);pos=b*2.65+k
                if len(values):
                    jitter=np.linspace(-.18,.18,len(values))
                    ax.scatter(pos+jitter,values,color=COLORS[c],alpha=.78,s=31,zorder=3)
                    ax.plot([pos-.30,pos+.30],[np.median(values)]*2,color=COLORS[c],lw=3,zorder=4)
                short_name='通常' if c=='normal' else '不整合'
                ax.text(pos,-.115,f'{short_name}\n{len(rows)}件',ha='center',va='top',fontsize=10,color=COLORS[c],transform=ax.get_xaxis_transform())
        ax.set_xticks([.5,3.15,5.8],[BATCHES[x] for x in BATCHES]);ax.tick_params(axis='x',length=0,pad=6)
        ax.set_ylabel(ylabel);ax.grid(axis='y',alpha=.7);ax.set_xlim(-.6,6.9)
        if key=='recorded_total_tokens' and log_tokens:
            ax.set_yscale('log');ax.set_ylabel('記録済み総トークン（百万・対数目盛）')
            ax.yaxis.set_major_locator(LogLocator(base=10,subs=(1,2,5)))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value:g}'))
            ax.yaxis.set_minor_locator(NullLocator())
        else:ax.set_ylim(bottom=0)
    axes[1].set_ylim(-3,105)
    emit(fig,'02-batch-distributions',['runs'],['Muse Spark 1.2のみ。合格率は評価出力であり有効品質ではない。'])

    fig,ax=plt.subplots(figsize=(12,7.2));header(fig,3,'記録済みトークンと保存済み評価結果','色は条件、形は取得バッチ。1点が1 Runで、両指標を記録した提出物を表示')
    ax.set_position([.085,.17,.70,.62])
    for batch,marker in [('previous','o'),('additional','^')]:
        for c in NAMES:
            sub=[r for r in primary if r['batch']==batch and r['condition']==c and r['recorded_total_tokens'] is not None and r['recorded_pass_rate'] is not None]
            ax.scatter([r['recorded_total_tokens']/1e6 for r in sub],[r['recorded_pass_rate'] for r in sub],
                color=COLORS[c],marker=marker,s=60,alpha=.80,edgecolor='white',linewidth=.6,label=BATCHES[batch]+'・'+NAMES[c])
    ax.set_xlabel('記録済み総トークン（百万）');ax.set_ylabel('保存済みv6の合格率（%）');ax.set_ylim(-3,105);ax.set_xlim(left=0);ax.grid(alpha=.6)
    ax.legend(loc='upper left',bbox_to_anchor=(1.015,1),frameon=False,fontsize=11)
    emit(fig,'03-tokens-pass-rate',['runs'],['同一条件内でも消費量の因果効果を示す図ではない。'])

    fig,axes=plt.subplots(1,2,figsize=(12,11.8));header(fig,4,'予定ペア内の差と、バッチ別の不確実性','差は「不整合条件 − 通常条件」。予定ペアは実行順のブロックで、共通の乱数種ではない')
    fig.subplots_adjust(left=.15,right=.97,top=.83,bottom=.17,wspace=.30)
    for ax,key,metric,scale in [(axes[0],'token_difference','記録済み総トークンの差（百万）',1e6),(axes[1],'pass_rate_difference_pp','保存済み合格率の差（ポイント）',1)]:
        for j,p in enumerate(pairs):
            if p[key] is None or not p['primary_model_pair']:
                ax.text(.03,j,'欠測',transform=ax.get_yaxis_transform(),ha='left',va='center',fontsize=9,color=GREY)
                continue
            ax.hlines(j,0,p[key]/scale,color='#B7C6D0',lw=1)
            ax.scatter(p[key]/scale,j,color=COLORS['normal'] if p['batch']=='previous' else COLORS['anti'],s=30)
        ax.axvline(0,color=GREY,lw=1);ax.axhline(9.5,color='#A6B2BA',ls='--');ax.set_ylim(len(pairs)-.5,-.5)
        ax.set_yticks(range(len(pairs)),[(('前回' if p['batch']=='previous' else '追加')+f" {p['pair_id']:02}") for p in pairs],fontsize=9)
        ax.set_xlabel(metric);ax.grid(axis='x',alpha=.5)
        limits=[r for r in tables['bootstrap'] if r['metric']==key]
        note='\n'.join(f"{BATCHES[r['stratum']]}：{r['mean']/scale:+.2f}［{r['lower']/scale:+.2f}, {r['upper']/scale:+.2f}］" for r in limits)
        ax.text(0,-.105,'平均差［95%区間］\n'+note,transform=ax.transAxes,va='top',fontsize=10,linespacing=1.5)
    emit(fig,'04-paired-differences',['pairs','bootstrap'],['20,000回、seed 20260911。バッチ内の完全な予定ペアを単位とするpercentile bootstrap。'])

    ff=tables['features'];order=list(dict.fromkeys(r['feature_id'] for r in ff));matrix=[];labels=[]
    for fid in order:
        values=[]
        for b in BATCHES:
            for c in NAMES:
                r=next(x for x in ff if x['stratum']==b and x['condition']==c and x['model']==MODEL and x['feature_id']==fid)
                values.append(np.nan if r['mean_pass_rate'] is None else r['mean_pass_rate'])
        matrix.append(values);labels.append(fid+' '+r['title']+f"（{r['ids_per_run'] or '?'} ID）")
    fig,ax=plt.subplots(figsize=(12,12));header(fig,5,'20機能の合格率を、バッチ別に比較','各セルは対象機能のID合格率（%）。すべてのIDを等配点とし、機能間の対象ID数は異なる')
    ax.set_position([.39,.12,.54,.70]);m=np.ma.masked_invalid(np.array(matrix));plot=ax.imshow(m,vmin=0,vmax=100,cmap='Blues',aspect='auto')
    ax.set_xticks(range(6),[BATCHES[b]+'\n'+NAMES[c] for b in BATCHES for c in NAMES],fontsize=11)
    ax.set_yticks(range(20),labels,fontsize=11)
    for i,row in enumerate(matrix):
        for j,v in enumerate(row):ax.text(j,i,'—' if np.isnan(v) else f'{v:.0f}',ha='center',va='center',fontsize=10,color='white' if v>=62 else INK)
    for x in [1.5,3.5]:ax.axvline(x,color='white',lw=3)
    for spine in ax.spines.values():spine.set_visible(False)
    cax=fig.add_axes([.49,.045,.34,.017]);fig.colorbar(plot,cax=cax,orientation='horizontal',label='保存済みv6の合格率（%）')
    emit(fig,'05-feature-heatmap',['features'],['機能別は各対象IDの保存済み合否の集計。未到達を機能全体の実装欠如と断定しない。'])

    evidence=read(BASE/'reviews/approval-path.json')
    fig,ax=plt.subplots(figsize=(12,7.6));header(fig,6,'承認者の前提と、後続評価を対応させる',evidence['subtitle'])
    ax.set_position([.04,.07,.92,.73]);ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
    box(ax,.03,.73,.29,.20,evidence['request'],GREY,'#F1F3F5')
    box(ax,.41,.73,.25,.20,evidence['expected'],COLORS['normal'])
    box(ax,.41,.40,.25,.20,evidence['observed'],COLORS['anti'],'#FAF1E6')
    arrow(ax,(.33,.83),(.40,.83));arrow(ax,(.33,.78),(.40,.51))
    box(ax,.74,.73,.23,.20,evidence['first_assertion'],COLORS['normal'],size=11)
    box(ax,.74,.40,.23,.20,evidence['downstream'],COLORS['anti'],'#FAF1E6',11)
    arrow(ax,(.67,.83),(.73,.83));arrow(ax,(.67,.50),(.73,.50))
    box(ax,.035,.025,.93,.20,evidence['scope_note'],GREY,'#F1F3F5',11.5)
    emit(fig,'06-approval-path',['reviews/approval-path.json'],evidence['limits'])
    (output/'figure-trace.json').write_text(json.dumps({'font_file':font.name,'font_sha256':sha(font),'figures':trace},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'figures':len(trace),'png':6,'svg':6}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=BASE/'data/results.json');p.add_argument('--output',type=Path,default=BASE/'figures');a=p.parse_args();build(a.data,a.output)

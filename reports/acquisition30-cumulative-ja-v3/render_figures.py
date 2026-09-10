"""Japanese figures for the unpaired, two-condition 60-Run reanalysis."""
from pathlib import Path
import argparse,csv,json,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties,fontManager
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

BASE=Path(__file__).resolve().parent
COLORS={'normal':'#0072B2','anti':'#D55E00'}
LABELS={'normal':'通常（normal）','anti':'不整合（anti）'}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,default=BASE/'data');ap.add_argument('--output',type=Path,default=BASE/'figures');ap.add_argument('--font',type=Path,default=Path('/mnt/c/Windows/Fonts/YuGothR.ttc'));a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);fontManager.addfont(str(a.font));font=FontProperties(fname=str(a.font)).get_name()
    plt.rcParams.update({'font.family':font,'font.size':10,'axes.titlesize':13,'axes.labelsize':11,'axes.unicode_minus':False,
      'svg.hashsalt':'sample1-reanalysis-v3','figure.facecolor':'white','axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
    runs=read(a.data/'runs.json');stats=read(a.data/'analysis.json');trace=[]
    def save(fig,name,title,sources):
        fig.savefig(a.output/(name+'.png'),bbox_inches='tight',metadata={'Software':'Matplotlib; fixed v3 analysis'})
        fig.savefig(a.output/(name+'.svg'),bbox_inches='tight',metadata={'Date':None,'Creator':'sample1 v3'})
        trace.append({'file':name,'title':title,'data_files':{str(p.relative_to(a.data)):digest(p) for p in sources},'png_sha256':digest(a.output/(name+'.png')),'svg_sha256':digest(a.output/(name+'.svg'))})
        plt.close(fig)
    def box(ax,xy,size,text,color='#eef3f7',edge='#a0b2be',fontsize=11):
        x,y=xy;w,h=size
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.015,rounding_size=0.02',facecolor=color,edgecolor=edge))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=fontsize,linespacing=1.6)
    def arrow(ax,start,end):ax.annotate('',xy=end,xytext=start,arrowprops=dict(arrowstyle='->',lw=1.6,color='#526674'))

    fig,ax=plt.subplots(figsize=(11,6.4));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    ax.set_title('図1　同じ申請管理アプリを、仕様の異なる二群で実装する',pad=18)
    box(ax,(.03,.69),(.43,.22),'通常仕様（normal）\n共通ルール：100万円／詳細：100万円\n独立した実装 30 Run',color='#e5f2fa',edge=COLORS['normal'])
    box(ax,(.54,.69),(.43,.22),'不整合仕様（anti）\n共通ルール：100万円／詳細：50万円\n独立した実装 30 Run',color='#fff0e5',edge=COLORS['anti'])
    box(ax,(.16,.39),(.68,.17),'各Runの提出物と記録を固定\n同一モデル・共通指示・60分上限／途中の評価結果は返さない')
    arrow(ax,(.245,.69),(.37,.56));arrow(ax,(.755,.69),(.63,.56))
    box(ax,(.03,.10),(.43,.18),'記録済み総トークン\n通常30件・不整合30件\nusageが存在する量を集計')
    box(ax,(.54,.10),(.43,.18),'共通v6：100万円基準・57評価ID\n合格率あり：通常28件・不整合29件\n起動不能3件は合格率が欠測')
    arrow(ax,(.37,.39),(.245,.28));arrow(ax,(.63,.39),(.755,.28))
    save(fig,'01-study-design','実験条件と分析対象',[a.data/'runs.json'])

    fig,axes=plt.subplots(1,2,figsize=(12,4.4),layout='constrained');rng=np.random.default_rng(67)
    for j,(metric,mult,title,xlabel) in enumerate([('recorded_total_tokens',1e-6,'記録済み総トークン：各30件','記録済み総トークン（百万）'),('pass_rate',1,'保存済みv6の合格率','合格率（%）')]):
        ax=axes[j]
        for k,c in enumerate(('normal','anti')):
            vals=np.array([r[metric] for r in runs if r['condition']==c and r[metric] is not None])*mult;y=1-k
            bp=ax.boxplot([vals],positions=[y],orientation='horizontal',widths=.36,showfliers=False,patch_artist=True,manage_ticks=False)
            bp['boxes'][0].set(facecolor=COLORS[c],alpha=.14,edgecolor=COLORS[c]);bp['medians'][0].set(color='#152d3b',linewidth=2)
            ax.scatter(vals,y+rng.uniform(-.11,.11,len(vals)),s=27,color=COLORS[c],alpha=.75,zorder=3)
            ax.text(.02,y+.23,f'{LABELS[c]}：{len(vals)}件',transform=ax.get_yaxis_transform(),fontsize=10,color=COLORS[c])
        ax.set(title=title,xlabel=xlabel,ylim=(-.45,1.55),yticks=[]);ax.grid(axis='x',alpha=.18)
        if j==0:ax.set_xlim(0,70);ax.annotate('N-cf6129\n64.18百万',xy=(64.175188,1),xytext=(45,.45),arrowprops=dict(arrowstyle='-',color='#61727c'),fontsize=9)
        else:ax.set_xlim(-3,103)
    fig.suptitle('図2　二群の分布：平均だけでなく、重なりと端のRunを見る',fontsize=15)
    save(fig,'02-condition-distributions','二群の分布',[a.data/'runs.json'])

    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,limit,title in [(axes[0],70,'全60件の位置'),(axes[1],16.5,'主な分布の拡大（横軸のみ）')]:
        for c,marker in [('normal','o'),('anti','^')]:
            rr=[r for r in runs if r['condition']==c and r['score_available']]
            ax.scatter([r['recorded_total_tokens']/1e6 for r in rr],[r['pass_rate'] for r in rr],s=36,marker=marker,color=COLORS[c],alpha=.72,label=LABELS[c])
            missing=[r for r in runs if r['condition']==c and not r['score_available']]
            ax.scatter([r['recorded_total_tokens']/1e6 for r in missing],[-13]*len(missing),s=55,marker='x',color=COLORS[c])
        ax.axhspan(-20,-6,color='#f1f3f5',zorder=0);ax.axhline(-6,color='#d0d7dc',lw=.8,zorder=0)
        ax.set(xlim=(0,limit),ylim=(-20,103),xlabel='記録済み総トークン（百万）',ylabel='保存済みv6の合格率（%）',title=title)
        ax.set_yticks([-13,0,20,40,60,80,100],['欠測','0','20','40','60','80','100']);ax.grid(alpha=.15)
    for label,offset in [('N-cf6129',(-90,20)),('N-b81827',(-55,10)),('A-41824f',(-80,-28)),('N-724b28',(-145,45))]:
        r=next(r for r in runs if r['label']==label);ax=axes[0] if label=='N-cf6129' else axes[1]
        ax.annotate(label,(r['recorded_total_tokens']/1e6,r['pass_rate'] if r['score_available'] else -13),xytext=offset,textcoords='offset points',fontsize=8,arrowprops=dict(arrowstyle='-',color='#71808a'))
    fig.suptitle('図3　消費量と合格率：起動不能のRunも消費量から除かない',fontsize=15)
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncols=2,fontsize=9)
    save(fig,'03-tokens-and-scores','トークンと合格率',[a.data/'runs.json'])

    features=stats['features'];fids=sorted({r['feature_id'] for r in features})
    matrix=np.array([[next(r['pass_rate'] for r in features if r['feature_id']==fid and r['condition']==c) for c in ('normal','anti')] for fid in fids])
    ylabels=[]
    for fid in fids:
        r=next(r for r in features if r['feature_id']==fid);title=r['title'].replace('（申請番号採番・承認者決定）','').replace('（管理者機能）','').replace('（遷移定義）','')
        ylabels.append(f'{fid} {title} ［{r["id_count"]} ID］')
    fig,ax=plt.subplots(figsize=(8.4,9));im=ax.imshow(matrix,cmap='YlGnBu',vmin=0,vmax=100,aspect='auto')
    ax.set_xticks([0,1],['通常（28件）','不整合（29件）']);ax.xaxis.tick_top();ax.tick_params(length=0)
    ax.set_yticks(np.arange(len(fids)),ylabels,fontsize=9)
    for y in range(len(fids)):
        for x in range(2):ax.text(x,y,f'{matrix[y,x]:.1f}%',ha='center',va='center',color='white' if matrix[y,x]>65 else '#182a36',fontsize=10)
    for y in np.arange(.5,len(fids),1):ax.axhline(y,color='white',lw=1)
    fig.colorbar(im,ax=ax,pad=.04,shrink=.8,label='機能内の評価IDの平均合格率（%）')
    ax.set_title('図4　20機能の結果：同じ合格率の尺度で二群を見る',pad=38)
    fig.tight_layout();save(fig,'04-feature-results','機能別の平均合格率',[a.data/'features.csv'])

    with (a.data/'selected-request-trajectories.csv').open(encoding='utf-8-sig') as f:requests=list(csv.DictReader(f))
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    styles=[('N-cf6129','#6d489b','最大消費・合格率欠測'),('N-b81827',COLORS['normal'],'通常の最高合格数 51 ID'),('A-41824f',COLORS['anti'],'不整合の最大消費・37 ID')]
    for label,color,desc in styles:
        rows=[r for r in requests if r['label']==label];x=[int(r['recorded_request']) for r in rows]
        axes[0].plot(x,[int(r['input_tokens'])/1000 for r in rows],color=color,lw=1.6,label=f'{label}：{desc}')
        axes[1].plot(x,[int(r['cumulative_tokens'])/1e6 for r in rows],color=color,lw=2,label=f'{label}：{desc}')
    axes[0].set(title='応答ごとに記録された入力量',xlabel='当該Run内のusage記録順',ylabel='1応答の入力トークン（千）')
    axes[1].set(title='入力＋出力の累積',xlabel='当該Run内のusage記録順',ylabel='記録済み総トークンの累積（百万）')
    for ax in axes:ax.grid(alpha=.18);ax.set_xlim(left=0);ax.set_ylim(bottom=0)
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncols=1,fontsize=9)
    fig.suptitle('図6　高消費の3事例：応答回数と繰り返し計上される入力',fontsize=15)
    save(fig,'06-request-trajectories','選択した3事例のusage推移',[a.data/'selected-request-trajectories.csv'])

    fig,ax=plt.subplots(figsize=(11,7));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    ax.set_title('図5　合格しなかった三つの経路を、保存証拠で区別する',pad=17)
    rows=[(.68,'仕様の採用判断','A-ca85fc：50万円を部長へ割当て\n課長による詳細取得は403\n別の通知ケースでも部長が宛先','100万円を境にする共通評価と不一致\n承認者に依存する複数の操作へ現れる','#fff0e5'),
      (.38,'画面の入口','N-724b28：画面の描画で例外\nReact is not defined\n保存された評価は0 / 57','画面を経由する業務確認が進まない\n57項目が個別に欠けたとは言えない','#edf2f7'),
      (.08,'出力の細部','N-b81827：51 / 57だがCSVは不合格\nダウンロード名に\nfilename関連の余分な文字列','名称の検査で止まった保存結果\nCSVが全く作れないこととは異なる','#e5f2fa')]
    for y,stage,left,right,color in rows:
        ax.text(.015,y+.205,stage,fontsize=12,fontweight='bold',color='#203f50')
        box(ax,(.04,y),(.44,.17),left,color=color,fontsize=10);box(ax,(.55,y),(.41,.17),right,fontsize=10);arrow(ax,(.48,y+.085),(.55,y+.085))
    save(fig,'05-distinct-failure-paths','保存証拠で区別する三つの経路',[a.data/'runs.json'])
    # Non-numeric illustration evidence is bound separately from its Run values.
    trace[-1]['evidence_files']={str(p.relative_to(BASE)):digest(p) for p in [BASE/'source/saved-observations.json',BASE/'evidence/csv-failure-review.json']}
    (a.output/'figure-manifest.json').write_text(json.dumps({'font_name':font,'font_sha256':digest(a.font),'figures':trace},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'figures':len(trace),'japanese_font':font,'output':str(a.output)},ensure_ascii=False))

if __name__=='__main__':main()

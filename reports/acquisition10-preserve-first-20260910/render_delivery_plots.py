"""Render report figures using only the public Run JSON and pinned plotting runtime."""
import json,statistics,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
COLORS={'normal':'#3568A8','anti':'#B67523'}
MARKERS={'normal':'o','anti':'^'}

def render(out,rows):
 primary=[r for r in rows if r['run_id'] and r['model_id']=='muse-spark-1.2-contributor']
 fig,ax=plt.subplots(figsize=(8,5),layout='constrained')
 labels=[]
 for position,condition in enumerate(('normal','anti')):
  values=[r['total_tokens']/1e6 for r in primary if r['condition']==condition and r['total_tokens'] is not None]
  labels.append(f'{condition} (n={len(values)})')
  ax.scatter([position+(i-(len(values)-1)/2)*.035 for i in range(len(values))],values,
   color=COLORS[condition],marker=MARKERS[condition],edgecolor='#333333',linewidth=.5)
  if values:ax.hlines(statistics.median(values),position-.25,position+.25,color='black',linewidth=2)
 ax.set_xticks([0,1],labels);ax.set_ylabel('Gateway implementation tokens (millions)')
 ax.set_title('Muse Spark 1.2 Contributor / one dot per Run\nBlack line: median; missing totals omitted')
 ax.set_xlim(-.5,1.5);ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)
 fig.savefig(out/'token-distribution.png',dpi=180);plt.close(fig)
 for name,valid in [('tokens-quality.png',True),('tokens-raw-v6.png',False)]:
  fig,ax=plt.subplots(figsize=(8,5),layout='constrained');plotted=0
  for condition in ('normal','anti'):
   group=[r for r in primary if r['condition']==condition and r['total_tokens'] is not None
    and (r['quality_percent'] is not None if valid else r['evaluation_completed'] and r['passed'] is not None and r['denominator'])]
   plotted+=len(group)
   if not group:continue
   xs=[r['total_tokens']/1e6 for r in group]
   ys=[r['quality_percent'] if valid else 100*r['passed']/r['denominator'] for r in group]
   ax.scatter(xs,ys,color=COLORS[condition],marker=MARKERS[condition],edgecolor='#333333',linewidth=.5,label=f'{condition} (n={len(group)})')
   for row,x,y in zip(group,xs,ys):
    offset,align={'anti-008':((-8,9),'right'),'anti-007':((8,-14),'left'),
     'anti-009':((-8,-14),'right'),'anti-003':((-8,8),'right')}.get(row['planned_run'],((5,6),'left'))
    ax.annotate(row['planned_run'],(x,y),xytext=offset,textcoords='offset points',fontsize=7,ha=align)
  ax.set_xlabel('Gateway implementation tokens (millions)')
  ax.set_ylabel('Validated quality / 57 IDs (%)' if valid else 'Raw v6 passed IDs / 57 (%)')
  title='Tokens and validated quality' if valid else 'Tokens and raw v6 results'
  subtitle=f'Valid coordinate pairs: {plotted}; {len(primary)} acquired Runs retained' if valid else f'Unvalidated raw results; n={plotted}; missing totals omitted'
  ax.set_title(title+' / Muse Spark 1.2\n'+subtitle)
  xmax=max([r['total_tokens']/1e6 for r in primary if r['total_tokens'] is not None]+[1])
  ax.set_ylim(-2,103);ax.set_xlim(0,max(10,xmax*1.1));ax.grid(alpha=.2)
  if plotted:ax.legend()
  else:
   text='No validated quality values selected\nRaw results and all Run records are retained' if valid else 'No complete token + raw result pairs'
   ax.text(.5,.5,text,ha='center',va='center',transform=ax.transAxes,color='#555555')
  fig.savefig(out/name,dpi=180);plt.close(fig)

if __name__=='__main__':
 destination=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
 render(destination,json.loads((destination/'runs.json').read_text(encoding='utf-8')))

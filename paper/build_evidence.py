"""Render manuscript evidence from frozen results; no model fitting or resampling."""
from pathlib import Path
import hashlib,json,os
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'paper/evidence';OUT.mkdir(exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'analysis/.mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
INPUTS=set();BLOCKS={}
def read(name):
 p=ROOT/'analysis'/f'{name}.csv';INPUTS.add(p);return pd.read_csv(p)
def fig(label,title,body,note):
 return '\n'.join([r'\begin{figure}[htbp]',r'\centering',body,r'\caption{'+title+r'}\label{fig:'+label+'}',r'\begin{minipage}{\linewidth}\footnotesize '+note,r'\end{minipage}',r'\end{figure}'])
def panel(body,opts):
 return r'\begin{minipage}{0.49\linewidth}\centering\begin{tikzpicture}\begin{axis}[paperaxis,width=.96\linewidth,height=5.4cm,'+opts+']\n'+body+'\n'+r'\end{axis}\end{tikzpicture}\end{minipage}'
def coords(x,y):return ' '.join(f'({a:.8g},{b:.8g})' for a,b in zip(x,y))
def preview(fig,name):
 fig.tight_layout();fig.savefig(OUT/(name+'.png'),dpi=200);fig.savefig(OUT/(name+'.pdf'));plt.close(fig)
q=read('revision_profiles');q=q[(q['sample']=='matched')&(q.flow=='Net migration')&(q.scale=='percent_gross')&(q.metric=='mean_absolute')&q.age.isin([6,9,12,15])]
a=read('annual_phases/annual_bootstrap');a=a[(a['sample']=='annual_matched')&(a.flow=='Net migration')&(a.metric=='mean_absolute')&(a.block==6)]
rows=[];panels=[];f,axs=plt.subplots(1,2,figsize=(6.3,3.0),sharey=True)
for ax,country,letter in zip(axs,['New Zealand','Australia'],['a','b']):
 body=''
 for frame,metric,lo,hi,label,color,marker,offset in [(q,'value','ci_low','ci_high','Quarter','paperblue','*',-.12),(a,'value','low','high','Annual','paperorange','square*',.12)]:
  g=frame[frame.country==country].sort_values('age');assert len(g)==4
  points=' '.join(f'({r.age+offset:.2f},{getattr(r,metric):.8f}) += (0,{getattr(r,hi)-getattr(r,metric):.8f}) -= (0,{getattr(r,metric)-getattr(r,lo):.8f})' for r in g.itertuples())
  body+=r'\addplot+[color='+color+',mark='+marker+r',error bars/.cd,y dir=both,y explicit] coordinates {'+points+'};\n'+r'\addlegendentry{'+label+'}\n'
  vals=g[metric].to_numpy();ax.errorbar(g.age+offset,vals,yerr=np.array([vals-g[lo],g[hi]-vals]),marker='o' if label=='Quarter' else 's',color='#21618c' if label=='Quarter' else '#b9600b',capsize=3,label=label)
  for r in g.itertuples():rows.append(dict(country=country,aggregation=label,age=r.age,n=r.n,value=getattr(r,metric),low=getattr(r,lo),high=getattr(r,hi)))
 opts=r'title={('+letter+') '+country+r'},xmin=5,xmax=16,ymin=0,ymax=6.5,xtick={6,9,12,15},xlabel={Months after period end},legend style={at={(0.98,0.98)},anchor=north east,font=\scriptsize},'
 if letter=='a':opts+=r'ylabel={Mean absolute revision (\% of gross)},'
 panels.append(panel(body,opts));ax.set(title=f'({letter}) {country}',xticks=[6,9,12,15],ylim=(0,6.5),xlabel='Months after period end');ax.grid(axis='y',alpha=.15);ax.legend(frameon=False)
axs[0].set_ylabel('Mean absolute revision (% of gross)');preview(f,'01_revision_profiles')
pd.DataFrame(rows).to_csv(OUT/'profile_intervals.csv',index=False)
BLOCKS['FIG_PROFILES']=fig('profiles','Net revision magnitude by information age','\n\\hfill\n'.join(panels),r'Common 24 endpoints, 2019Q2--2025Q1; 18-month reference. Points are mean absolute revisions divided by the corresponding quarterly or annual reference gross count. Whiskers are pointwise 95\% stationary-bootstrap sensitivity intervals with mean block length six quarters. Horizontal offsets separate the series; no intermediate ages are evaluated.')
# Expand the already specified threshold grid to annual targets using existing revisions.
m=read('monitoring_first_age');d=read('annual_phases/annual_revision_periods');d=d[d.balanced&(d.flow=='Net migration')&d.age.isin([6,9,12,15])]
cohorts=[('NZ quarterly (24)','matched','New Zealand'),('AU quarterly (24)','matched','Australia'),('NZ annual / quarter ends (24)','annual_matched','New Zealand'),('AU annual / quarter ends (24)','annual_matched','Australia'),('NZ annual / month ends (75)','annual_nz','New Zealand')]
thresholds=[.5,1,2,5];requirements=[.8,.9,.95];grid=[];records=[]
for label,sample,country in cohorts:
 row=[]
 for tol in thresholds:
  for req in requirements:
   if sample=='matched':
    z=m[(m['sample']==sample)&(m.country==country)&(m.flow=='Net migration')&(m.tolerance==tol)&(m.required_attainment==req)];assert len(z)==1
    age=z.first_stable_age.iloc[0];n=int(z.n.iloc[0])
   else:
    g=d[(d['sample']==sample)&(d.country==country)];n=g.period.nunique();rates=g.groupby('age').scaled_revision.agg(lambda x:(x.abs()<=tol).mean())
    age=next((int(h) for h in [6,9,12,15] if (rates.loc[h:]>=req).all()),np.nan)
   row.append(age);records.append(dict(cohort=label,tolerance=tol,required_attainment=req,first_age=age,n=n))
 grid.append(row)
grid=np.array(grid);pd.DataFrame(records).to_csv(OUT/'monitoring_grid.csv',index=False)
assert np.array_equal(grid[:,7],np.array([15,15,9,12,12]))
colors={6:'paperblue!18',9:'paperblue!35',12:'paperblue!55',15:'paperblue!82'}
body=[r'\begin{tikzpicture}[x=0.67cm,y=0.56cm,font=\small]']
for j,tol in enumerate(thresholds):body.append(r'\node[font=\scriptsize] at ('+str(j*3+1.5)+r',1.25) {'+str(tol)+r'\% tolerance};')
for j in range(12):body.append(r'\node[font=\scriptsize] at ('+str(j+.5)+',.55) {'+str(int(requirements[j%3]*100))+r'\%};')
for i,(label,_,_) in enumerate(cohorts):
 body.append(r'\node[anchor=east,font=\scriptsize] at (-.15,'+str(-i-.5)+') {'+label+'};')
 for j,v in enumerate(grid[i]):
  fill='black!7' if np.isnan(v) else colors[int(v)];ink='white' if v==15 else 'black';vlabel='--' if np.isnan(v) else str(int(v))
  body.append(r'\filldraw[fill='+fill+r',draw=white] ('+str(j)+','+str(-i)+') rectangle ('+str(j+1)+','+str(-i-1)+');')
  body.append(r'\node[text='+ink+'] at ('+str(j+.5)+','+str(-i-.5)+') {'+vlabel+'};')
body.append(r'\draw[black,line width=.8pt] (7,0) rectangle (8,-5);')
body.append(r'\node[anchor=west,font=\scriptsize] at (0,-5.65) {Cell = first qualifying age (months); -- = not met at any tested age};')
body.append(r'\end{tikzpicture}')
BLOCKS['FIG_GRID']=fig('grid','Monitoring horizons across tolerances and attainment requirements','\n'.join(body),r'Tolerances are percentages of reference gross migration; column subheadings are required attainment proportions. Qualification must persist through all later tested ages in $\{6,9,12,15\}$. The outlined column is the illustrative 2\%/90\% rule. Counts in parentheses are endpoints, not independent observations.')
f,ax=plt.subplots(figsize=(8.3,3.2));mapping={6:0,9:1,12:2,15:3};vals=np.array([[mapping.get(v,4) for v in r] for r in grid]);cmap=ListedColormap(['#d8e5ed','#b1cada','#86acc5','#427c9f','#eeeeee']);ax.imshow(vals,cmap=cmap,vmin=0,vmax=4,aspect='auto')
ax.set(yticks=range(5),yticklabels=[c[0] for c in cohorts],xticks=range(12),xticklabels=[f'{t}%\n{int(r*100)}%' for t in thresholds for r in requirements],xlabel='Tolerance / required attainment')
for i in range(5):
 for j in range(12):ax.text(j,i,'—' if np.isnan(grid[i,j]) else str(int(grid[i,j])),ha='center',va='center',color='white' if grid[i,j]==15 else 'black')
ax.add_patch(plt.Rectangle((6.5,-.5),1,5,fill=False,lw=1.1,color='black'));preview(f,'02_monitoring_grid')
# Component offsets: same four endpoint phases in both countries.
c=read('annual_phases/phase_components_original');c=c[(c['sample']=='matched')&(c.age==6)]
phases=['pre_2020','restrictions_2020_21','reopening_2022','later_2023_25'];labs=['2019','2020--21','2022','2023--25Q1'];body='';f,ax=plt.subplots(figsize=(6.3,3.1))
for country,color,offset in [('New Zealand','paperblue',-.16),('Australia','paperorange',.16)]:
 g=c[c.country==country].set_index('phase').loc[phases];ys=100*g.offset_fraction.to_numpy();xs=np.arange(4)+offset
 body+=r'\addplot+[mark=none,ybar,area legend,bar width=10pt,bar shift=0pt,fill='+color+',draw='+color+(',pattern=north east lines,pattern color=black' if color=='paperorange' else '')+'] coordinates {'+coords(xs,ys)+'};\n'+r'\addlegendentry{'+country+'}\n'
 ax.bar(xs,ys,width=.29,label=country,color='#21618c' if country=='New Zealand' else '#b9600b',hatch='' if country=='New Zealand' else '///')
axis=r'\begin{tikzpicture}\begin{axis}[paperaxis,width=.94\linewidth,height=5.7cm,ymin=-55,ymax=110,xmin=-.6,xmax=3.6,xtick={0,1,2,3},xticklabels={2019,2020--21,2022,2023--25Q1},ylabel={Component offset (\%)},xlabel={Reference-endpoint phase},legend style={at={(.5,1.02)},anchor=south,legend columns=2,font=\small}]'
BLOCKS['FIG_COMPONENTS']=fig('components','Offsetting and amplification of component revisions',axis+'\n'+body+r'\addplot[black,forget plot] coordinates {(-.6,0)(3.6,0)};\end{axis}\end{tikzpicture}',r'Six-month quarterly revisions, common 24 endpoints. Positive values indicate offsetting in equation~\eqref{eq:offset}; negative values indicate amplification. The four phases contain 3, 8, 4 and 9 quarters, respectively. Values are descriptive and retain the published net/component rounding residual.')
ax.axhline(0,color='#555',lw=.8);ax.set(xticks=range(4),xticklabels=['2019','2020–21','2022','2023–25Q1'],ylabel='Component offset (%)',ylim=(-55,110));ax.legend(frameon=False,ncol=2);ax.grid(axis='y',alpha=.15);preview(f,'03_component_offsets');c.to_csv(OUT/'component_offsets.csv',index=False)
# Benchmark coverage and yearly score gains on already paired predictions.
b=read('revision_benchmark/summary');b=b[(b['sample']=='Native cadence')&(b.country=='New Zealand')];y=read('revision_benchmark/by_year');y=y[(y['sample']=='Native cadence')&(y.country=='New Zealand')&(y.flow=='Net migration')];w=y.pivot(index='year',columns='method',values='mean_score');gains=100*(1-w['Empirical revision']/w['Published model']);counts=y[y.method=='Empirical revision'].set_index('year').n
f,axs=plt.subplots(1,2,figsize=(6.5,3.0));body=''
for method,label,color,off in [('Published model','Model','paperorange',-.15),('Empirical revision','Revision','paperblue',.15)]:
 z=b[b.method==method].set_index('flow').loc[['Arrivals','Departures','Net migration']];x=np.arange(3)+off
 body+=r'\addplot+[mark=none,ybar,area legend,bar width=8pt,bar shift=0pt,fill='+color+',draw='+color+(',pattern=north east lines,pattern color=black' if color=='paperorange' else '')+'] coordinates {'+coords(x,z.coverage_pct)+'};\n'+r'\addlegendentry{'+label+'}\n'
 axs[0].bar(x,z.coverage_pct,width=.28,label=label,color='#b9600b' if method=='Published model' else '#21618c',hatch='///' if method=='Published model' else '')
left=panel(body,r'title={(a) Reference coverage},xmin=-.5,xmax=2.5,ymin=0,ymax=115,xtick={0,1,2},xticklabels={Arrivals,Departures,Net},ylabel={Coverage (\%)},legend style={at={(.5,1.0)},anchor=north,legend columns=2,font=\scriptsize}')
body=r'\addplot+[mark=none,ybar,area legend,bar width=14pt,fill=paperblue,draw=paperblue] coordinates {'+coords(np.arange(4),gains)+'};\n'+r'\addplot[black] coordinates {(-.5,0)(3.5,0)};'
right=panel(body,r'title={(b) Net score reduction},xmin=-.5,xmax=3.5,ymin=-100,ymax=100,xtick={0,1,2,3},xticklabels={2022,2023,2024,2025},ylabel={Score reduction (\%)},xlabel={Reference-endpoint year}')
BLOCKS['FIG_BENCHMARK']=fig('benchmark','Average benchmark gains and their limits',left+'\n\\hfill\n'+right,r'New Zealand, same 33 monthly annual endpoints and six-month snapshots for both methods. Panel (a) concerns containment of the 18-month reference, not calibration for the published model estimand. Positive score reductions in panel (b) favor the empirical revision interval. Endpoint-year counts are 6, 12, 12 and 3; 2022 covers July--December and 2025 January--March. Mean width is reported in Table~\ref{tab:benchmark}.')
axs[0].set(xticks=range(3),xticklabels=['Arrivals','Departures','Net'],ylim=(0,115),ylabel='Coverage (%)',title='(a) Reference coverage');axs[0].legend(frameon=False,ncol=2,fontsize=8)
axs[1].bar(range(4),gains,color='#21618c');axs[1].axhline(0,color='#555',lw=.8);axs[1].set(xticks=range(4),xticklabels=[f'{j}\n(n={counts[j]})' for j in gains.index],ylim=(-100,100),ylabel='Score reduction (%)',title='(b) Net score reduction')
for ax in axs:ax.grid(axis='y',alpha=.15)
preview(f,'04_benchmark_limits');b.to_csv(OUT/'benchmark_coverage.csv',index=False);pd.DataFrame({'year':gains.index,'n':counts,'score_reduction_pct':gains}).to_csv(OUT/'benchmark_years.csv',index=False)
# Compact selected block-length sensitivity, including a flagged degenerate case.
a=read('annual_phases/annual_bootstrap');m=read('monitoring_attainment');out=[];lines=[]
for country,label in [('New Zealand','NZ'),('Australia','AU')]:
 for length in [4,6,8]:
  r=a[(a['sample']=='annual_matched')&(a.country==country)&(a.flow=='Net migration')&(a.age==6)&(a.metric=='mean_absolute')&(a.block==length)].iloc[0]
  out.append(dict(target=label+' annual mean absolute revision',block=length,n=r.n,value=r.value,low=r.low,high=r.high,units='percent gross'))
  lines.append(f'{label} annual mean absolute revision & {length} quarters & {r.value:.2f} & [{r.low:.2f}, {r.high:.2f}]'+r' \\')
for length in [12,18,24]:
 r=a[(a['sample']=='annual_nz')&(a.flow=='Net migration')&(a.age==6)&(a.metric=='revision_coverage')&(a.block==length)].iloc[0]
 out.append(dict(target='NZ annual model-interval reference coverage',block=length,n=r.n,value=100*r.value,low=100*r.low,high=100*r.high,units='percent endpoints'))
 lines.append(f'NZ annual reference coverage & {length} months & {100*r.value:.1f} & [{100*r.low:.1f}, {100*r.high:.1f}]'+r' \\')
pd.DataFrame(out).to_csv(OUT/'block_sensitivity.csv',index=False)
BLOCKS['TABLE_BLOCKS']=r'''\begin{table}[htbp]\centering\small
\caption{Selected six-month estimates under alternative bootstrap block lengths}\label{tab:blocks}
\begin{tabular}{l l r r}\toprule
Quantity & Mean block & Estimate & 95\% interval\\\midrule
'''+ '\n'.join(lines)+r'''
\bottomrule\end{tabular}
\begin{minipage}{\linewidth}\footnotesize Mean absolute net revisions use 24 quarter-end annual totals and are percentages of reference gross migration. Coverage uses 75 monthly annual endpoints and is the percentage whose published model interval contains the 18-month net reference. Intervals are pointwise stationary-bootstrap sensitivity intervals, not future-coverage guarantees.\end{minipage}
\end{table}'''
# Detailed figures and tables are regenerated from retained result files only.
(OUT/'blocks.json').write_text(json.dumps(BLOCKS,indent=2))
(OUT/'provenance.json').write_text(json.dumps({'operation':'Descriptive summaries and figures only; no fitting or resampling','inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(INPUTS)},'threshold_cells':len(records),'profile_points':len(rows)},indent=2))
if __name__=='__main__':
 print(pd.DataFrame(records).pivot(index='cohort',columns=['tolerance','required_attainment'],values='first_age').to_string())
 print('Saved four figure previews, embedded LaTeX blocks and source tables.')

"""Populate manuscript tables and numerical claims from stored results; no estimation."""
from pathlib import Path
import re,json,hashlib,runpy
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'paper'
values={};audit=[];inputs=set()
def select(file,filters):
 p=ROOT/'analysis'/f'{file}.csv';inputs.add(p)
 d=pd.read_csv(p)
 for k,v in filters.items():d=d[d[k]==v]
 assert len(d)==1,(file,filters,len(d))
 return d.iloc[0]
def claim(key,file,filters,field,dp=2,mult=1,absolute=False):
 r=select(file,filters);v=float(r[field])*mult
 if absolute:v=abs(v)
 values[key]=f'{v:,.{dp}f}'
 audit.append(dict(id=key,file=f'analysis/{file}.csv',filters=json.dumps(filters),field=field,multiplier=mult,absolute=absolute,raw_value=v,printed=values[key]))
 return values[key]
denominator = runpy.run_path(str(OUT/'denominator_sensitivity.py'))
values.update(denominator['BLOCKS']); inputs.update(denominator['INPUTS'])
claim('NZ_CURRENT_A9_HITS','denominator_sensitivity/attainment',dict(cohort='NZ annual / quarter ends',denominator='contemporaneous_gross',age=9),'hits',0)
claim('NZ_CURRENT_A9_RATE','denominator_sensitivity/attainment',dict(cohort='NZ annual / quarter ends',denominator='contemporaneous_gross',age=9),'attainment',1,100)
for denom,key in [('reference_gross','NZ_REFERENCE_HORIZON'),('contemporaneous_gross','NZ_CURRENT_HORIZON')]:
 claim(key,'denominator_sensitivity/horizons',dict(cohort='NZ annual / quarter ends',denominator=denom),'first_age',0)
base={'sample':'matched','flow':'Net migration','scale':'percent_gross','metric':'mean_absolute'}
for short,country in [('NZ','New Zealand'),('AU','Australia')]:
 for age in [6,15]:claim(f'{short}_Q{age}','revision_profiles',dict(base,country=country,age=age),'value')
 claim(f'{short}_Q12_HITS','monitoring_attainment',dict(sample='matched',country=country,flow='Net migration',tolerance=2,age=12),'hits',0)
 claim(f'{short}_A6','annual_phases/annual_profiles',dict(sample='annual_matched',country=country,flow='Net migration',age=6),'mean_absolute')
 claim(f'{short}_FLIPS','direction_summary',dict(sample='matched',country=country,age=6,deadband_percent=0,metric='strict_flip_rate'),'events',0)
 for phase,suf in [('pre_2020','2019'),('reopening_2022','2022'),('later_2023_25','LATER')]:
  claim(f'{short}_OFFSET_{suf}','annual_phases/phase_components_original',dict(sample='matched',country=country,age=6,phase=phase),'offset_fraction',1,100)
  claim(f'{short}_REV_{suf}','annual_phases/phase_profiles_original',dict(sample='matched',country=country,age=6,phase=phase,flow='Net migration'),'mean_absolute')
claim('NZ_A9_HITS','annual_phases/annual_profiles',dict(sample='annual_matched',country='New Zealand',age=9,flow='Net migration'),'hits',0)
for field,key,dp,mult in [('hits','NZ_ALL_A9_HITS',0,1),('attainment','NZ_ALL_A9_RATE',1,100)]:
 claim(key,'annual_phases/annual_profiles',dict(sample='annual_nz',country='New Zealand',age=9,flow='Net migration'),field,dp,mult)
for age in [6,15]:
 for field,suf,dp,mult in [('hits','_HITS',0,1),('coverage','',1,100)]:
  claim(f'NZ_ALL_COV{age}{suf}','annual_phases/annual_interval_summary',dict(group='all',flow='Net migration',age=age),field,dp,mult)
for age,ref,key in [(6,18,'NZ_REF6_HITS'),(15,18,'NZ_REF15_18_HITS'),(15,24,'NZ_REF15_24_HITS')]:
 claim(key,'annual_phases/annual_reference_interval_coverage',dict(flow='Net migration',age=age,reference_age=ref),'hits',0)
for field,key in [('score_reduction_pct','NZ_NET_SCORE_GAIN'),('width_ratio','NZ_NET_WIDTH_RATIO'),('scaled_score_reduction_pct','NZ_NET_SCALED_GAIN')]:
 claim(key,'revision_benchmark/paired_comparison',dict(sample='Native cadence',flow='Net migration'),field,1)
for field,key in [('benchmark_better','NZ_NET_WINS'),('official_better','NZ_NET_LOSSES')]:
 claim(key,'revision_benchmark/paired_comparison',dict(sample='Native cadence',flow='Net migration'),field,0)
for method,suf in [('Published model','OLD'),('Empirical revision','NEW')]:
 for field,key in [('mean_width',f'NZ_B_NET_WIDTH_{suf}'),('mean_score',f'NZ_B_NET_SCORE_{suf}'),('hits',f'NZ_B_NET_HITS_{suf}')]:
  claim(key,'revision_benchmark/summary',dict(sample='Native cadence',country='New Zealand',flow='Net migration',method=method),field,0)
claim('NZ_B_COV_OLD','revision_benchmark/summary',dict(sample='Native cadence',country='New Zealand',flow='Net migration',method='Published model'),'coverage_pct',1)
for flow,short in [('Arrivals','ARR'),('Departures','DEP')]:
 for field,key,dp in [('hits',f'NZ_B_{short}_HITS',0),('coverage_pct',f'NZ_B_{short}_COV',1),('misses_below',f'NZ_B_{short}_MISSES',0)]:
  claim(key,'revision_benchmark/summary',dict(sample='Native cadence',country='New Zealand',flow=flow,method='Empirical revision'),field,dp)
claim('NZ_DEP_WIDTH_RATIO','revision_benchmark/paired_comparison',dict(sample='Native cadence',flow='Departures'),'width_ratio',1)
for year in [2022,2023,2024,2025]:
 f='revision_benchmark/by_year'; filt=dict(sample='Native cadence',country='New Zealand',flow='Net migration',year=year)
 old=select(f,dict(filt,method='Published model')).mean_score
 new=select(f,dict(filt,method='Empirical revision')).mean_score
 key=f'NZ_NET_{"GAIN" if new<old else "LOSS"}_{year}';v=abs(100*(new/old-1));values[key]=f'{v:.1f}'
 audit.append(dict(id=key,file=f'analysis/{f}.csv',filters=json.dumps(filt),field='abs(100*(empirical mean_score/published mean_score-1))',raw_value=v,printed=values[key]))
for field,key,dp in [('hits','AU_B_NET_HITS',0),('coverage_pct','AU_B_NET_COV',1)]:
 claim(key,'revision_benchmark/summary',dict(sample='Native cadence',country='Australia',flow='Net migration',method='Empirical revision'),field,dp)
claim('AU_B_NET_2022_HITS','revision_benchmark/by_year',dict(sample='Native cadence',country='Australia',flow='Net migration',method='Empirical revision',year=2022),'hits',0)
claim('AU_B_COMP_COV','revision_benchmark/summary',dict(sample='Native cadence',country='Australia',flow='Arrivals',method='Empirical revision'),'coverage_pct',1)
claim('NZ_SHARED_OLD_HITS','revision_benchmark/summary',dict(sample='Shared quarter ends',country='New Zealand',flow='Net migration',method='Published model'),'hits',0)
claim('AU_SHARED_HITS','revision_benchmark/summary',dict(sample='Shared quarter ends',country='Australia',flow='Net migration',method='Empirical revision'),'hits',0)
claim('NZ_SHARED_SCORE_GAIN','revision_benchmark/paired_comparison',dict(sample='Shared quarter ends',flow='Net migration'),'score_reduction_pct',1)

def table(label,title,spec,header,rows,note):
 return '\n'.join([r'\begin{table}[htbp]',r'\centering\small',r'\caption{'+title+r'}\label{tab:'+label+'}',r'\begin{tabular}{'+spec+'}',r'\toprule',header+r' \\',r'\midrule',*[' & '.join(row)+r' \\' for row in rows],r'\bottomrule',r'\end{tabular}',r'\par\smallskip\begin{minipage}{\linewidth}\footnotesize '+note,r'\end{minipage}',r'\end{table}'])
rows=[]
for age in [6,9,12,15]:
 row=[str(age)]
 for country in ['New Zealand','Australia']:
  row.append(claim(f'T1_{country}_{age}_Q','revision_profiles',dict(base,country=country,age=age),'value'))
  row.append(claim(f'T1_{country}_{age}_A','annual_phases/annual_profiles',dict(sample='annual_matched',country=country,age=age,flow='Net migration'),'mean_absolute'))
 rows.append(row)
values['TABLE_PROFILES']=table('profiles','Mean absolute net revisions by information age','r r r r r',r'Age (months) & NZ quarterly & NZ annual & AU quarterly & AU annual',rows,r'Percent of the corresponding 18-month reference gross flow. All columns use the same 24 endpoints, 2019Q2--2025Q1. Quarterly and annual denominators differ because they refer to different aggregation periods. Annual New Zealand totals are published values; Australian totals are constructed within each vintage.')
rows=[]
for country,short in [('New Zealand','NZ'),('Australia','AU')]:
 for phase,title in [('pre_2020','2019Q2--Q4'),('restrictions_2020_21','2020--2021'),('reopening_2022','2022'),('later_2023_25','2023Q1--2025Q1')]:
  filters=dict(sample='matched',country=country,age=6,phase=phase)
  n=select('annual_phases/phase_components_original',filters)['n']
  rows.append([short,title,str(int(n)),claim(f'T2_{short}_{phase}_rev','annual_phases/phase_profiles_original',dict(filters,flow='Net migration'),'mean_absolute'),claim(f'T2_{short}_{phase}_offset','annual_phases/phase_components_original',filters,'offset_fraction',1,100)])
values['TABLE_PHASES']=table('phases','Quarterly revisions and component offsetting at six months','l l r r r',r'Country & Reference periods & $n$ & Mean abs. revision & Offset (\%)',rows,r'Mean absolute net revisions are percentages of reference gross flow. Offset is $100\times2\overline{r_A r_D}/(\overline{r_A^2}+\overline{r_D^2})$. Negative values indicate amplification. Phase labels group reference quarters, not publication dates, and do not identify causal effects.')
rows=[]
for age in [2,6,9,12,15]:
 fil=dict(group='all',flow='Net migration',age=age)
 rows.append([str(age),claim(f'T3_{age}_hits','annual_phases/annual_interval_summary',fil,'hits',0)+'/75',claim(f'T3_{age}_coverage','annual_phases/annual_interval_summary',fil,'coverage',1,100),claim(f'T3_{age}_width','annual_phases/annual_interval_summary',fil,'mean_width',0), '['+claim(f'T3_{age}_low','annual_phases/annual_bootstrap',dict(sample='annual_nz',flow='Net migration',age=age,metric='revision_coverage',block=18),'low',1,100)+', '+claim(f'T3_{age}_high','annual_phases/annual_bootstrap',dict(sample='annual_nz',flow='Net migration',age=age,metric='revision_coverage',block=18),'high',1,100)+']'])
values['TABLE_COVERAGE']=table('coverage','NZ annual model intervals and subsequent net migration references','r r r r r',r'Age & Covered & Coverage (\%) & Mean width & 95\% sensitivity interval',rows,r'75 monthly annual endpoints, January 2019--March 2025. Intervals equal the published annual estimate $\pm1.96$ published annual standard errors. Width is in migration counts. Ages are months after period end. Coverage concerns the 18-month published reference, not the original model-uncertainty target. The final column is a pointwise stationary-bootstrap interval for that historical coverage percentage (mean block length 18 months), distinct from the published model interval.')
rows=[]
for flow,short in [('Arrivals','Arrivals'),('Departures','Departures'),('Net migration','Net')]:
 for method,display in [('Published model','Model'),('Empirical revision','Revision')]:
  fil=dict(sample='Native cadence',country='New Zealand',flow=flow,method=method)
  rows.append([short,display,claim(f'T4_{short}_{display}_hits','revision_benchmark/summary',fil,'hits',0)+'/33',claim(f'T4_{short}_{display}_width','revision_benchmark/summary',fil,'mean_width',0),claim(f'T4_{short}_{display}_score','revision_benchmark/summary',fil,'mean_score',0)])
values['TABLE_BENCHMARK']=table('benchmark','NZ six-month annual intervals on identical benchmark test cases','l l r r r',r'Flow & Interval & References covered & Mean width & Mean score',rows,r"""33 monthly annual endpoints, July 2022--March 2025; 18-month references. ``Model'' denotes the published estimate $\pm1.96$ annual standard errors. ``Revision'' denotes the exploratory central empirical revision interval. Width and 95\% interval score are in count units; lower score is better. No cross-flow score ranking is intended.""")
evidence=runpy.run_path(str(OUT/'build_evidence.py'))
values.update(evidence['BLOCKS']);inputs.update(evidence['INPUTS'])
checks=runpy.run_path(str(OUT/'submission_checks.py'))
values.update(checks['BLOCKS']);inputs.update(ROOT/p for p in checks['INPUTS'])
for block in re.findall(r'\\begin\{table\}.*?\\end\{table\}',(OUT/'context_tables.tex').read_text(encoding='utf-8'),re.S):
 key=re.search(r'\\label\{([^}]+)\}',block).group(1)
 values['CONTEXT_'+key]=block
(OUT/'evidence_blocks.json').write_text(json.dumps(values,indent=2),encoding='utf-8')
text='\n\n'.join('% '+key+'\n'+value for key,value in values.items())
(OUT/'Numerical_Evidence.tex').write_text(text,encoding='utf-8')
pd.DataFrame(audit).to_csv(OUT/'numerical_claims.csv',index=False)
(OUT/'draft_provenance.json').write_text(json.dumps({'type':'Numerical evidence from existing outputs; no models estimated','sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs)},'numeric_entries':len(audit)},indent=2))
print('Numeric claims and table entries:',len(audit))
print('paper/Numerical_Evidence.tex')


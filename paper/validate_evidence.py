"""Check embedded manuscript evidence against stored observation-level results."""
from pathlib import Path
import json,re,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'paper/evidence'
s=(ROOT/'paper/Numerical_Evidence.tex').read_text()
q=pd.read_csv(ROOT/'analysis/revision_periods.csv');a=pd.read_csv(ROOT/'analysis/annual_phases/annual_revision_periods.csv')
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
for r in pd.read_csv(OUT/'monitoring_grid.csv').itertuples():
 country='New Zealand' if r.cohort.startswith('NZ') else 'Australia'
 sample='matched' if 'quarterly' in r.cohort else 'annual_nz' if 'month ends' in r.cohort else 'annual_matched'
 data=q if sample=='matched' else a
 g=data[(data['sample']==sample)&(data.country==country)&(data.flow=='Net migration')&data.balanced&data.age.isin([6,9,12,15])]
 rates={h:float((z.scaled_revision.abs()<=r.tolerance).mean()) for h,z in g.groupby('age')}
 h=next((h for h in [6,9,12,15] if all(rates[k]>=r.required_attainment for k in rates if k>=h)),np.nan)
 check('grid '+r.cohort+f' {r.tolerance}/{r.required_attainment}',g.period.nunique()==r.n and (np.isnan(h) and np.isnan(r.first_age) or h==r.first_age))
for r in pd.read_csv(OUT/'profile_intervals.csv').itertuples():
 data=q if r.aggregation=='Quarter' else a;sample='matched' if r.aggregation=='Quarter' else 'annual_matched'
 g=data[(data['sample']==sample)&(data.country==r.country)&(data.flow=='Net migration')&data.balanced&(data.age==r.age)]
 check('profile '+r.country+f' {r.aggregation}/{r.age}',len(g)==r.n and np.isclose(g.scaled_revision.abs().mean(),r.value) and r.low<=r.value<=r.high)
example=a[(a['sample']=='annual_nz')&(a.country=='New Zealand')&(a.flow=='Net migration')&(a.period=='2023-12')&(a.age==6)].iloc[0]
check('tolerance example',example.gross==331815 and example.reference_count==127951 and round(.02*example.gross)==6636 and round(100*.02*example.gross/example.reference_count,1)==5.2)
p=pd.read_csv(ROOT/'analysis/revision_benchmark/predictions.csv')
for r in pd.read_csv(OUT/'benchmark_coverage.csv').itertuples():
 g=p[(p.country=='New Zealand')&(p.flow==r.flow)&(p.method==r.method)]
 check('benchmark coverage '+r.flow+r.method,len(g)==r.n and np.isclose(100*((g.lower<=g.target)&(g.target<=g.upper)).mean(),r.coverage_pct))
for r in pd.read_csv(OUT/'benchmark_years.csv').itertuples():
 g=p[(p.country=='New Zealand')&(p.flow=='Net migration')&(pd.to_datetime(p.reference).dt.year==r.year)]
 values=g.groupby('method').score.mean();v=100*(1-values['Empirical revision']/values['Published model'])
 check('benchmark year '+str(r.year),np.isclose(v,r.score_reduction_pct) and len(g)==2*r.n)
claims=pd.read_csv(ROOT/'paper/numerical_claims.csv')
for r in claims.to_dict('records'):
 d=pd.read_csv(ROOT/r['file'])
 for k,v in json.loads(r['filters']).items():d=d[d[k]==v]
 if r['field'] in d:
  check('unique source '+r['id'],len(d)==1)
  mult=r.get('multiplier',1);mult=1 if pd.isna(mult) else mult
  value=float(d.iloc[0][r['field']])*mult
  if r.get('absolute') is True:value=abs(value)
 else:
  value=abs(100*(d[d.method=='Empirical revision'].mean_score.iloc[0]/d[d.method=='Published model'].mean_score.iloc[0]-1))
 check('claim '+r['id'],np.isclose(value,r['raw_value'],rtol=1e-12,atol=1e-12) and str(r['printed']) in s)
check('four embedded figures',s.count(r'\begin{figure}')==4 and r'\includegraphics' not in s)
check('no unresolved placeholders','{{' not in s)
prov=json.loads((OUT/'provenance.json').read_text())
for file,digest in prov['inputs'].items():check('input unchanged '+file,hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==digest)
(OUT/'validation.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'source_sha256':hashlib.sha256(s.encode()).hexdigest()},indent=2))
print(f'{len(checks)} checks passed; 60 threshold cells, 16 profile points, benchmark panels and {len(claims)} numerical entries verified.')


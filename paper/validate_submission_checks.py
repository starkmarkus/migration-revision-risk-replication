"""Independently recount the added checks from retained panels and source values."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/submission_checks'
checks = []
def check(name, ok):
    assert ok, name
    checks.append(name)

q = pd.read_csv(ROOT/'analysis/asof_panel.csv')
a = pd.read_csv(ROOT/'analysis/annual_phases/annual_asof_panel.csv')
specs = {
    'NZ quarterly': (q, 'matched', 'New Zealand'),
    'AU quarterly': (q, 'matched', 'Australia'),
    'NZ annual / quarter ends': (a, 'annual_matched', 'New Zealand'),
    'AU annual / quarter ends': (a, 'annual_matched', 'Australia'),
    'NZ annual / month ends': (a, 'annual_nz', 'New Zealand')}
mon = pd.read_csv(ROOT/'results/nz_vintages.csv')
mon['reference'] = pd.to_datetime(mon.reference).dt.to_period('M')
au = pd.read_csv(ROOT/'analysis/source_observations.csv')
au = au[au.country == 'Australia'].copy()
au['reference'] = pd.to_datetime(au.reference).dt.to_period('Q')
source_nz = mon.set_index(['frequency', 'vintage_period', 'reference', 'flow']).estimate
source_au = au.set_index(['vintage_period', 'reference', 'flow']).estimate
checked_sources = set()

def value(label, period, age, flow):
    panel, sample, country = specs[label]
    z = panel[(panel['sample'] == sample) & (panel.country == country) & (panel.period == period)
              & (panel.age == age) & (panel.flow == flow)]
    assert len(z) == 1
    r = z.iloc[0]
    key = (label, period, age, flow)
    if key not in checked_sources:
        if country == 'New Zealand':
            end = pd.Timestamp(r.reference).to_period('M')
            if 'annual' in label:
                original = source_nz.loc[('Year ended', r.vintage_period, end, flow)]
            else:
                original = sum(source_nz.loc[('Monthly', r.vintage_period, t, flow)]
                               for t in pd.period_range(end-2, end, freq='M'))
        else:
            end = pd.Timestamp(r.reference).to_period('Q')
            periods = pd.period_range(end-3, end, freq='Q') if 'annual' in label else [end]
            original = sum(source_au.loc[(r.vintage_period, t, flow)] for t in periods)
        check('source value '+str(key), np.isclose(original, r.estimate, rtol=0, atol=1e-8))
        checked_sources.add(key)
    return r.estimate

obs = pd.read_csv(OUT/'monitoring_observations.csv')
for r in obs.itertuples():
    gross = value(r.cohort, r.period, 18, 'Arrivals') + value(r.cohort, r.period, 18, 'Departures')
    v = 100*(value(r.cohort, r.period, 18, 'Net migration')-value(r.cohort, r.period, r.age, 'Net migration'))/gross
    check('monitoring revision '+str((r.cohort,r.period,r.age)), np.isclose(v,r.scaled_revision) and (abs(v)<=2)==r.qualifies)

ref = pd.read_csv(OUT/'reference_observations.csv')
for r in ref.itertuples():
    gross = value(r.cohort,r.period,r.reference_age,'Arrivals')+value(r.cohort,r.period,r.reference_age,'Departures')
    target = value(r.cohort,r.period,r.reference_age,'Net migration')
    early = value(r.cohort,r.period,r.age,'Net migration')
    check('later reference '+str((r.cohort,r.period,r.age,r.reference_age)),
          np.allclose([r.gross,r.target,r.early,r.scaled_revision], [gross,target,early,100*(target-early)/gross]))
for label, g in ref.groupby('cohort'):
    check('identical endpoints '+label, set(g[g.reference_age==18].period)==set(g[g.reference_age==24].period))
for r in pd.read_csv(OUT/'reference_profiles.csv').itertuples():
    g = ref[(ref.cohort==r.cohort)&(ref.reference_age==r.reference_age)&(ref.age==r.age)]
    check('reference profile '+str((r.cohort,r.reference_age,r.age)),
          len(g)==r.n and np.isclose(g.scaled_revision.abs().mean(),r.mean_absolute)
          and int((g.scaled_revision.abs()<=2).sum())==r.hits and np.isclose(r.hits/r.n,r.attainment))

for r in pd.read_csv(OUT/'attainment_counts.csv').itertuples():
    g=obs[(obs.cohort==r.cohort)&(obs.age==r.age)]
    if r.omitted_year!='none':g=g[g.year!=int(r.omitted_year)]
    check('year count '+str((r.cohort,r.omitted_year,r.age)),len(g)==r.n and int(g.qualifies.sum())==r.hits)
for r in pd.read_csv(OUT/'leave_year_out.csv').itertuples():
    g=obs[obs.cohort==r.cohort]
    if r.omitted_year!='none':g=g[g.year!=int(r.omitted_year)]
    rates=g.groupby('age').qualifies.mean()
    candidates=[h for h in [6,9,12,15] if min(rates.loc[h:])>=.9]
    first=min(candidates) if candidates else np.nan
    check('year horizon '+str((r.cohort,r.omitted_year)), g.period.nunique()==r.n and
          (first==r.first_age or np.isnan(first) and np.isnan(r.first_age)))

cal=pd.read_csv(ROOT/'analysis/release_calendar.csv',parse_dates=['release','available'])
dates=pd.read_csv(OUT/'publication_observations.csv',parse_dates=['reference','cutoff','release','available'])
for r in dates.itertuples():
    c=cal[(cal.country==r.country)&(cal.release<=r.cutoff)].sort_values('release').iloc[-1]
    check('calendar selection '+str((r.cohort,r.period,r.age)),c.vintage_period==r.vintage_period
          and c.available==r.available and c.release==r.release and r.available<=r.cutoff)
    check('calendar durations '+str((r.cohort,r.period,r.age)),
          [(r.release-r.reference).days,(r.available-r.reference).days,(r.cutoff-r.available).days,(r.available-r.release).days]
          ==[r.release_age_days,r.file_age_days,r.cutoff_gap_days,r.file_delay_days])
for r in pd.read_csv(OUT/'adjacent_editions.csv').itertuples():
    g=dates[(dates.cohort==r.cohort)&(dates.period==r.period)].set_index('age')
    same=g.loc[r.age_from,'vintage_period']==g.loc[r.age_to,'vintage_period'] and g.loc[r.age_from,'file']==g.loc[r.age_to,'file']
    check('edition reuse '+str((r.cohort,r.period,r.age_from,r.age_to)),same==r.same_edition)

provenance=json.loads((OUT/'provenance.json').read_text())
for path,sha in provenance['inputs'].items():check('frozen input '+path,hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha)
check('generator source',hashlib.sha256((ROOT/'paper/submission_checks.py').read_bytes()).hexdigest()==provenance['script_sha256'])
paper=(ROOT/'paper/Numerical_Evidence.tex').read_text()
for key,block in json.loads((OUT/'blocks.json').read_text()).items():check('embedded table '+key,block in paper)
check('two changing year omissions',sum(r.first_age != pd.read_csv(OUT/'leave_year_out.csv').query('cohort == @r.cohort and omitted_year == "none"').first_age.iloc[0]
      for r in pd.read_csv(OUT/'leave_year_out.csv').itertuples() if r.omitted_year!='none')==2)
(OUT/'validation.json').write_text(json.dumps(dict(passed=len(checks),source_values_verified=len(checked_sources),
    scope='Frozen source-value reconstruction, reference profiles, endpoint-year counts/horizons and calendar selection; no refitting',
    numerical_evidence_sha256=hashlib.sha256(paper.encode()).hexdigest(),checks=checks),indent=2))
print(f'{len(checks)} checks passed; {len(checked_sources)} selected counts reconstructed from retained source-value tables.')

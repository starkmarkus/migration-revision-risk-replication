"""Compare reference and contemporaneous gross denominators on fixed cohorts.

Added after the pre-submission review; descriptive, with no model selection.
The contemporaneous denominator uses both components of the same early edition.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/denominator_sensitivity'
OUT.mkdir(parents=True, exist_ok=True)
AGES = [6, 9, 12, 15]
INPUTS = set()
BLOCKS = {}

def read(name):
    p = ROOT / 'analysis' / (name + '.csv')
    INPUTS.add(p)
    return pd.read_csv(p)

q = read('revision_periods')
a = read('annual_phases/annual_revision_periods')
panels = {'quarterly': read('asof_panel'),
          'annual': read('annual_phases/annual_asof_panel')}
cohorts = [('NZ quarterly', 'matched', 'New Zealand', 'quarterly', q),
           ('AU quarterly', 'matched', 'Australia', 'quarterly', q),
           ('NZ annual / quarter ends', 'annual_matched', 'New Zealand', 'annual', a),
           ('AU annual / quarter ends', 'annual_matched', 'Australia', 'annual', a),
           ('NZ annual / month ends', 'annual_nz', 'New Zealand', 'annual', a)]
observations, counts, horizons = [], [], []
keys = ['sample', 'country', 'period', 'age', 'vintage_period']
for label, sample, country, frequency, revisions in cohorts:
    panel = panels[frequency]
    components = panel[panel.flow.isin(['Arrivals', 'Departures'])]
    gross = components.pivot(index=keys, columns='flow', values='estimate')
    gross['contemporaneous_gross'] = gross.Arrivals + gross.Departures
    d = revisions[(revisions['sample'] == sample) & (revisions.country == country)
                  & (revisions.flow == 'Net migration') & revisions.balanced
                  & revisions.age.isin(AGES)].copy()
    d = d.merge(gross[['contemporaneous_gross']].reset_index(), on=keys,
                how='left', validate='one_to_one')
    assert len(d) == 4 * d.period.nunique()
    assert d[['gross', 'contemporaneous_gross']].notna().all().all()
    assert (d[['gross', 'contemporaneous_gross']] > 0).all().all()
    assert (pd.to_datetime(d.available) <= pd.to_datetime(d.cutoff)).all()
    d['cohort'] = label
    d['reference_gross'] = d.gross
    for denominator in ['reference_gross', 'contemporaneous_gross']:
        d[denominator + '_hit'] = d.revision.abs() <= .02 * d[denominator]
        rates = {}
        for age in AGES:
            z = d[d.age == age]
            hits = int(z[denominator + '_hit'].sum())
            rates[age] = hits / len(z)
            counts.append(dict(cohort=label, denominator=denominator, age=age,
                               hits=hits, n=len(z), attainment=hits / len(z)))
        h = next((h for h in AGES if all(rates[k] >= .9 for k in AGES if k >= h)), np.nan)
        horizons.append(dict(cohort=label, denominator=denominator,
                             first_age=h, n=d.period.nunique()))
    observations.append(d[['cohort', 'sample', 'country', 'period', 'age', 'cutoff',
                           'vintage_period', 'available', 'estimate', 'reference_count',
                           'revision', 'reference_gross', 'contemporaneous_gross',
                           'reference_gross_hit', 'contemporaneous_gross_hit']])

obs = pd.concat(observations, ignore_index=True)
c = pd.DataFrame(counts)
h = pd.DataFrame(horizons)
obs.to_csv(OUT/'observations.csv', index=False)
c.to_csv(OUT/'attainment.csv', index=False)
h.to_csv(OUT/'horizons.csv', index=False)
obs[obs.reference_gross_hit != obs.contemporaneous_gross_hit].to_csv(OUT/'changed_classifications.csv', index=False)
rows = []
for label, *_ in cohorts:
    z = c[(c.cohort == label) & (c.age == 9)].set_index('denominator')
    v = h[h.cohort == label].set_index('denominator')
    rows.append(' & '.join([label,
        str(int(v.loc['reference_gross', 'first_age'])),
        str(int(v.loc['contemporaneous_gross', 'first_age'])),
        f"{int(z.loc['reference_gross','hits'])}/{int(z.loc['reference_gross','n'])}",
        f"{int(z.loc['contemporaneous_gross','hits'])}/{int(z.loc['contemporaneous_gross','n'])}"]) + r' \\')
BLOCKS['TABLE_DENOMINATORS'] = r'''\begin{table}[htbp]\centering\small
\caption{Monitoring horizons under two gross-flow denominators}\label{tab:denominators}
\begin{tabular}{l r r r r}\toprule
 & \multicolumn{2}{c}{First qualifying age} & \multicolumn{2}{c}{Nine-month hits/$n$}\\
Target & Reference & Current & Reference & Current\\\midrule
''' + '\n'.join(rows) + r'''
\bottomrule\end{tabular}
\par\smallskip\begin{minipage}{\linewidth}\footnotesize
Absolute net revisions within 2\% of the stated gross denominator in at least 90\% of endpoints, with persistence through later tested ages in $\{6,9,12,15\}$. Ages are months. Reference gross is arrivals plus departures at 18 months. Current gross uses arrivals plus departures from the same early edition as the net estimate, at each tested age. The revision numerator, later reference and balanced endpoints are held fixed. Both are retrospective attainment assessments; only the current tolerance scale is observable at the early origin.\end{minipage}
\end{table}'''
(OUT/'provenance.json').write_text(json.dumps({
    'status': 'Descriptive sensitivity added after pre-submission review; no fitting or retuning',
    'ages': AGES, 'reference_age': 18, 'tolerance': .02, 'attainment': .9,
    'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(INPUTS)},
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
}, indent=2), encoding='utf-8')
print(h.pivot(index='cohort', columns='denominator', values='first_age').to_string())

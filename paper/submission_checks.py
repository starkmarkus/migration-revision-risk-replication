"""Reference, release-calendar and endpoint-year checks on frozen observations."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/submission_checks'
OUT.mkdir(exist_ok=True)
AGES = [6, 9, 12, 15]
INPUTS = {}

def read(name):
    p = ROOT / 'analysis' / (name + '.csv')
    INPUTS[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return pd.read_csv(p)

def save(rows, name):
    d = pd.DataFrame(rows)
    d.to_csv(OUT / (name + '.csv'), index=False)
    return d

def first_age(rates):
    return next((h for h in AGES if all(rates[k] >= .9 for k in AGES if k >= h)), np.nan)

qp, ap = read('asof_panel'), read('annual_phases/annual_asof_panel')
qr, ar = read('revision_periods'), read('annual_phases/annual_revision_periods')
calendar = read('release_calendar')
cohorts = [
    ('NZ quarterly', 'matched', 'New Zealand', qp, qr),
    ('AU quarterly', 'matched', 'Australia', qp, qr),
    ('NZ annual / quarter ends', 'annual_matched', 'New Zealand', ap, ar),
    ('AU annual / quarter ends', 'annual_matched', 'Australia', ap, ar),
    ('NZ annual / month ends', 'annual_nz', 'New Zealand', ap, ar),
]
refs, ref_profiles, ref_horizons, eligibility = [], [], [], []
timing, adjacent, counts, years, influence = [], [], [], [], []
for label, sample, country, panel, revisions in cohorts:
    base = revisions[(revisions['sample'] == sample) & (revisions.country == country)
                     & revisions.balanced & revisions.age.isin(AGES) & (revisions.flow == 'Net migration')].copy()
    periods = set(base.period)
    assert len(base) == len(periods) * 4
    p = panel[(panel['sample'] == sample) & (panel.country == country) & panel.period.isin(periods)].copy()
    for col in ['reference', 'release', 'available', 'cutoff']:
        p[col] = pd.to_datetime(p[col])
    later = p[p.age == 24].pivot(index='period', columns='flow', values='estimate')
    eligible = set(later.dropna().index)
    for period in sorted(periods):
        g = p[(p.period == period) & (p.age == 24)]
        eligibility.append(dict(cohort=label, period=period, eligible24=period in eligible,
            reason='available' if period in eligible else '; '.join(sorted(set(g.missing_reason.dropna())))))
    # Restrict both reference definitions to the exact same endpoints. The main
    # cohort is held fixed before checking the availability of a later reference.
    for reference_age in [18, 24]:
        if not eligible:
            ref_horizons.append(dict(cohort=label, reference_age=reference_age, n=0, first_age=np.nan))
            continue
        target = p[(p.age == reference_age) & p.period.isin(eligible)].pivot(index='period', columns='flow', values='estimate')
        target['gross'] = target.Arrivals + target.Departures
        assert (target.gross > 0).all()
        g = base[base.period.isin(eligible)].merge(target[['Net migration', 'gross']], left_on='period', right_index=True, suffixes=('_old', ''))
        g['scaled'] = 100 * (g['Net migration'] - g.estimate) / g.gross
        g['target'] = g['Net migration']
        rates = {}
        for age, z in g.groupby('age'):
            hits = int((z.scaled.abs() <= 2).sum()); rates[int(age)] = hits / len(z)
            ref_profiles.append(dict(cohort=label, reference_age=reference_age, age=age, n=len(z),
                mean_absolute=z.scaled.abs().mean(), hits=hits, attainment=hits / len(z)))
            for r in z.itertuples():
                refs.append(dict(cohort=label, period=r.period, age=age, reference_age=reference_age,
                    early=r.estimate, target=r.target, gross=r.gross, scaled_revision=r.scaled))
        ref_horizons.append(dict(cohort=label, reference_age=reference_age, n=len(eligible),
            first_age=first_age(rates) if len(rates) == 4 else np.nan))
    # Calendar quantities are measured in days. They do not measure how much
    # traveller history an agency actually used in its production system.
    pn = p[(p.flow == 'Net migration') & p.age.isin(AGES + [18])].copy()
    for r in pn.itertuples():
        timing.append(dict(cohort=label, country=country, period=r.period, age=r.age,
            reference=r.reference, cutoff=r.cutoff, release=r.release, available=r.available,
            vintage_period=r.vintage_period, file=r.file,
            release_age_days=(r.release-r.reference).days,
            file_age_days=(r.available-r.reference).days,
            cutoff_gap_days=(r.cutoff-r.available).days,
            file_delay_days=(r.available-r.release).days))
    for period, g in pn.groupby('period'):
        g = g.set_index('age')
        for h1, h2 in zip(AGES, AGES[1:] + [18]):
            same = (g.loc[h1, 'vintage_period'] == g.loc[h2, 'vintage_period']
                    and g.loc[h1, 'file'] == g.loc[h2, 'file'])
            adjacent.append(dict(cohort=label, period=period, age_from=h1, age_to=h2, same_edition=bool(same)))
    base['year'] = pd.to_datetime(base.reference).dt.year
    for omitted in [None] + sorted(base.year.unique().tolist()):
        g = base if omitted is None else base[base.year != omitted]
        rates = {}
        for age, z in g.groupby('age'):
            hits = int((z.scaled_revision.abs() <= 2).sum()); rates[int(age)] = hits / len(z)
            counts.append(dict(cohort=label, omitted_year='none' if omitted is None else int(omitted),
                age=int(age), hits=hits, n=len(z), attainment=hits / len(z)))
        years.append(dict(cohort=label, omitted_year='none' if omitted is None else int(omitted),
            n=g.period.nunique(), first_age=first_age(rates)))
    # Retain the endpoint-level successes for an independent recount.
    for r in base.itertuples():
        influence.append(dict(cohort=label, period=r.period, year=r.year, age=r.age,
            scaled_revision=r.scaled_revision, qualifies=abs(r.scaled_revision) <= 2))

save(refs, 'reference_observations')
save(ref_profiles, 'reference_profiles')
horizons = save(ref_horizons, 'reference_horizons')
save(eligibility, 'reference_eligibility')
time = save(timing, 'publication_observations')
stats = time.groupby(['cohort', 'age']).agg(n=('period', 'size'),
    release_age_min=('release_age_days', 'min'), release_age_median=('release_age_days', 'median'), release_age_max=('release_age_days', 'max'),
    file_age_min=('file_age_days', 'min'), file_age_median=('file_age_days', 'median'), file_age_max=('file_age_days', 'max'),
    cutoff_gap_min=('cutoff_gap_days', 'min'), cutoff_gap_median=('cutoff_gap_days', 'median'), cutoff_gap_max=('cutoff_gap_days', 'max'),
    delayed_files=('file_delay_days', lambda x: int((x > 0).sum())), max_file_delay=('file_delay_days', 'max')).reset_index()
save(stats, 'publication_summary')
paired = time[time.cohort.isin(['NZ quarterly', 'AU quarterly'])].pivot(
    index=['period', 'age'], columns='country', values='file_age_days')
paired['AU_minus_NZ_days'] = paired.Australia - paired['New Zealand']
save(paired.reset_index(), 'paired_publication_ages')
save(paired.groupby('age').AU_minus_NZ_days.agg(['min', 'median', 'max']).reset_index(), 'paired_publication_summary')
adj = save(adjacent, 'adjacent_editions')
save(adj.groupby(['cohort', 'age_from', 'age_to']).agg(n=('period', 'size'), same_edition=('same_edition', 'sum')).reset_index(), 'edition_reuse_summary')
count_table = save(counts, 'attainment_counts')
loo = save(years, 'leave_year_out')
save(influence, 'monitoring_observations')
(OUT/'provenance.json').write_text(json.dumps(dict(
    status='Descriptive follow-up after inspecting main results; no fitted models, new bootstrap or significance tests',
    requirements=dict(tolerance_percent_gross=2, attainment=.9, ages=AGES,
        reference='18 versus 24 on identical eligible endpoints; denominator follows reference',
        omission='one reference-endpoint calendar year at a time, including partial years; no retraining'),
    inputs=INPUTS, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=2))

def table(label, title, spec, header, rows, note):
    return '\n'.join([r'\begin{table}[htbp]\centering\small',
        r'\caption{'+title+r'}\label{tab:'+label+'}', r'\begin{tabular}{'+spec+'}',
        r'\toprule', header+r'\\\midrule', *[' & '.join(r)+r'\\' for r in rows],
        r'\bottomrule\end{tabular}', r'\par\smallskip\begin{minipage}{\linewidth}\footnotesize '+note,
        r'\end{minipage}', r'\end{table}'])

BLOCKS = {}
rows = []
for label, *_ in cohorts:
    all_ = count_table[(count_table.cohort == label) & (count_table.omitted_year == 'none')].set_index('age')
    h = int(loo[(loo.cohort == label) & (loo.omitted_year == 'none')].first_age.iloc[0])
    prev = AGES[AGES.index(h)-1]
    omitted = loo[(loo.cohort == label) & (loo.omitted_year != 'none')].first_age
    span = str(int(omitted.min())) if omitted.min() == omitted.max() else f'{int(omitted.min())}--{int(omitted.max())}'
    rows.append([label, str(h), f'{prev}: {int(all_.loc[prev,"hits"])}/{int(all_.loc[prev,"n"])}',
                 f'{h}: {int(all_.loc[h,"hits"])}/{int(all_.loc[h,"n"])}', span])
omission_changes = []
for label, *_ in cohorts:
    group = loo[loo.cohort == label]
    full = int(group[group.omitted_year == 'none'].first_age.iloc[0])
    for r in group[group.omitted_year != 'none'].itertuples():
        if int(r.first_age) != full:
            omission_changes.append(f'{label} without {r.omitted_year} ({int(r.first_age)} months)')
omission_note = ('Changes under omission: ' + '; '.join(omission_changes) + '. '
                 if omission_changes else 'No omission changes a qualifying age. ')
BLOCKS['TABLE_INFLUENCE'] = table('influence', 'Monitoring counts and endpoint-year sensitivity',
    'l r r r r', r'Target & Full age & Previous: hits/$n$ & Qualifying: hits/$n$ & Omit-year ages', rows,
    r'Net revisions within 2\% of reference gross migration in at least 90\% of endpoints, with persistence through later tested ages. Ages are months. The last column gives the range after omitting each reference-endpoint year, 2019--2025, in turn; partial years are included. ' + omission_note + r'These are descriptive influence checks, not confidence limits.')
rows = []
profiles = pd.DataFrame(ref_profiles)
for label, *_ in cohorts:
    g = profiles[profiles.cohort == label]
    if g.empty:
        continue
    for age in AGES:
        a = g[(g.age == age) & (g.reference_age == 18)].iloc[0]
        b = g[(g.age == age) & (g.reference_age == 24)].iloc[0]
        rows.append([label, str(age), f'{a.mean_absolute:.3f}', f'{b.mean_absolute:.3f}',
            f'{int(a.hits)}/{int(a.n)}', f'{int(b.hits)}/{int(b.n)}'])
BLOCKS['TABLE_REFERENCE_PROFILES'] = table('referenceprofiles', 'Reference sensitivity on identical eligible endpoints',
    'l r r r r r', r'Target & Age & MAR (18) & MAR (24) & Hits/$n$ (18) & Hits/$n$ (24)', rows,
    r'MAR is mean absolute net revision as a percentage of gross migration at the stated reference age. Hits satisfy the 2\% tolerance. Quarterly and NZ quarter-end annual comparisons use 22 endpoints, 2019Q2--2024Q3; monthly annual comparisons use 69, January 2019--September 2024. Complete 24-month Australian annual targets are absent from the retained main-period archive. The later denominator changes with the reference; the evaluated early counts and endpoints are held fixed.')
rows = []
for label, short in [('NZ quarterly','NZ quarter ends'), ('AU quarterly','AU quarter ends'), ('NZ annual / month ends','NZ month ends')]:
    for r in stats[stats.cohort == label].itertuples():
        rows.append([short, str(r.age), str(r.n), f'{r.file_age_median:g} [{r.file_age_min}, {r.file_age_max}]',
                     f'{r.cutoff_gap_median:g} [{r.cutoff_gap_min}, {r.cutoff_gap_max}]', str(r.delayed_files)])
BLOCKS['TABLE_PUBLICATION_AGES'] = table('publicationages', 'Actual availability ages at the nominal cutoffs',
    'l r r r r r', r'Endpoints & Age & $n$ & File age: median [range] & Gap: median [range] & Delayed', rows,
    r'Nominal age is in months; file age and gap are in days. File age runs from the reference-period end to exact-file availability; gap runs from availability to the nominal cutoff. Delayed counts files available after their headline release date. Quarter-end dates apply to both quarterly and annual targets. Source dates and headline release ages are retained in the replication tables. No adjacent selected age pair, including 15 versus 18 months, reuses the same edition.')
(OUT/'blocks.json').write_text(json.dumps(BLOCKS, indent=2))
print(horizons.to_string(index=False))
print(stats[stats.age.isin([6,18])].to_string(index=False))
print(loo.pivot(index='cohort', columns='omitted_year', values='first_age').to_string())

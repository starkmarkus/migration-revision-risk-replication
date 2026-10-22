"""Annual publication revisions and descriptive calendar-phase stability."""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd
import openpyxl
from research import ROOT, FLOWS, AGES, FREEZE, cutoff, interval_score, uncertainty

OUT = ROOT / 'analysis' / 'annual_phases'
OUT.mkdir(exist_ok=True)
PHASES = ['pre_2020', 'restrictions_2020_21', 'reopening_2022', 'later_2023_25']

def save(df, name):
    df.to_csv(OUT / (name + '.csv'), index=False)
    return df

def phase(date):
    year = pd.Timestamp(date).year
    return PHASES[0] if year < 2020 else PHASES[1] if year <= 2021 else PHASES[2] if year == 2022 else PHASES[3]

def annual_sources():
    nz = pd.read_csv(ROOT/'results/nz_vintages.csv')
    nz = nz[nz.frequency == 'Year ended'].copy()
    nz['reference'] = pd.to_datetime(nz.reference).dt.to_period('M').dt.to_timestamp('M')
    nz['release'] = pd.to_datetime(nz.release)
    nz['available'] = nz.release
    nz['country'] = 'New Zealand'
    nz['file'] = 'nz_history.xlsx'
    nz['construction'] = 'published annual'
    source = pd.read_csv(ROOT/'analysis/source_observations.csv', parse_dates=['reference','available','release'])
    au = source[source.country == 'Australia'].copy()
    au['quarter'] = au.reference.dt.to_period('Q')
    records = []
    for (vintage, flow), g in au.groupby(['vintage_period','flow']):
        g = g.set_index('quarter').sort_index()
        for q in g.index:
            keys = pd.period_range(q - 3, q, freq='Q')
            if not keys.isin(g.index).all():
                continue
            sub = g.loc[keys]
            assert sub.file.nunique() == 1 and sub.available.nunique() == 1
            records.append(dict(country='Australia', flow=flow, reference=q.to_timestamp('Q'),
                vintage_period=vintage, estimate=sub.estimate.sum(), standard_error=np.nan,
                available=sub.available.iloc[0], release=sub.release.iloc[0], file=sub.file.iloc[0],
                construction='four exact quarters, one vintage'))
    annual = pd.concat([nz, pd.DataFrame(records)], ignore_index=True)
    assert not annual.duplicated(['country','vintage_period','reference','flow']).any()
    save(annual, 'annual_source_values')
    # Independently reread every published annual estimate and SE from original cells.
    workbook = openpyxl.load_workbook(ROOT/'raw/nz_history.xlsx', read_only=True, data_only=True)
    checks = []
    for flow, group in nz.groupby('flow'):
        rows = list(workbook[flow].values)
        fields = rows[4]
        for row in group.itertuples():
            start = int(row.source_column) - 1
            est_col = next(i for i in range(start, start+7) if str(fields[i]).startswith('Estimated '))
            se_col = next(i for i in range(start, start+7) if fields[i] == 'Standard error(1)')
            raw = rows[int(row.source_row)-1]
            assert raw[est_col] == row.estimate and raw[se_col] == row.standard_error
        checks.append(dict(check='annual estimate and SE cells', country='New Zealand', flow=flow, n=len(group), passed=True))
    save(pd.DataFrame(checks), 'source_checks')
    # Published annual values can differ from monthly sums; preserve, do not repair them.
    mon = source[source.country == 'New Zealand'].copy()
    mon['month'] = mon.reference.dt.to_period('M')
    rows = []
    for (v, f), group in nz.groupby(['vintage_period','flow']):
        m = mon[(mon.vintage_period == v)&(mon.flow == f)].set_index('month')
        for a in group.itertuples():
            p = a.reference.to_period('M'); keys = pd.period_range(p-11, p, freq='M')
            if keys.isin(m.index).all():
                total = m.loc[keys,'estimate'].sum()
                rows.append(dict(vintage=v, reference=a.reference, flow=f, annual=a.estimate,
                                 monthly_sum=total, difference=a.estimate-total))
    save(pd.DataFrame(rows), 'published_annual_vs_monthly_sum')
    return annual

def build_panel(annual):
    dates = pd.read_csv(ROOT/'analysis/release_calendar.csv', parse_dates=['release','available'])
    specs = [('annual_matched','2019Q1','2025Q1','Q',['New Zealand','Australia'],AGES),
             ('annual_nz','2019-01','2025-03','M',['New Zealand'],[2,3]+AGES),
             ('annual_au_extended','2011Q1','2025Q1','Q',['Australia'],AGES)]
    rows = []
    for sample, first, last, freq, countries, ages in specs:
        for country in countries:
            calendar = dates[(dates.country == country)&(dates.release <= FREEZE)].sort_values('release')
            source = annual[annual.country == country]
            lookup = {(v,t): g.set_index('flow') for (v,t),g in source.groupby(['vintage_period','reference'])}
            for p in pd.period_range(first,last,freq=freq):
                end = p.to_timestamp(how='end').normalize()
                months = pd.period_range(end.to_period('M')-11,end.to_period('M'),freq='M')
                composition = {ph: sum(phase(m.to_timestamp()) == ph for m in months) for ph in PHASES}
                for age in [0]+ages+[18,24]:
                    target = cutoff(end,age) if age else FREEZE
                    if age:
                        elig = calendar[calendar.release <= min(target,FREEZE)]
                        chosen = elig.iloc[-1] if len(elig) else None
                    else:
                        avail = source[source.reference == end].sort_values('available')
                        chosen = calendar[calendar.vintage_period == avail.vintage_period.iloc[0]].iloc[0] if len(avail) else None
                    reason = ''
                    if target > FREEZE:
                        reason = 'cutoff after freeze'
                    elif chosen is None:
                        reason = 'no released edition'
                    elif pd.isna(chosen.available) or chosen.available > target:
                        reason = 'latest exact file unavailable at cutoff'
                    elif (chosen.vintage_period,end) not in lookup:
                        reason = 'complete annual total absent from latest edition'
                    values = lookup.get((chosen.vintage_period,end)) if not reason else None
                    for flow in FLOWS:
                        v = values.loc[flow] if values is not None and flow in values.index else None
                        rows.append(dict(sample=sample,country=country,period=str(p),reference=end,
                            age=age,flow=flow,cutoff=target,phase=phase(end),fully_contained=max(composition.values()) == 12,
                            **{'months_'+ph: n for ph,n in composition.items()},
                            vintage_period=chosen.vintage_period if chosen is not None else '',
                            available=chosen.available if chosen is not None else pd.NaT,
                            release=chosen.release if chosen is not None else pd.NaT,
                            estimate=v.estimate if v is not None else np.nan,
                            standard_error=v.standard_error if v is not None else np.nan,
                            file=v.file if v is not None else '',missing_reason=reason))
    panel = pd.DataFrame(rows)
    assert not panel.duplicated(['sample','country','period','age','flow']).any()
    valid = panel[panel.estimate.notna()]
    assert (valid.available <= valid.cutoff).all() and (valid.release <= valid.cutoff).all()
    save(panel,'annual_asof_panel')
    save(panel.groupby(['sample','country','age','missing_reason']).agg(n=('estimate','size'),available=('estimate','count')).reset_index(),'annual_availability')
    return panel

def revisions(panel, ref=18):
    key = ['sample','country','period','flow']
    target = panel[panel.age == ref][key+['estimate','available']].rename(columns={'estimate':'reference_count','available':'reference_available'})
    data = panel[panel.age.isin([0,2,3]+AGES)].merge(target,on=key,validate='many_to_one')
    gross = target.pivot(index=key[:-1],columns='flow',values='reference_count')
    gross['gross'] = gross['Arrivals'] + gross['Departures']
    data = data.merge(gross[['gross']].reset_index(),on=key[:-1],validate='many_to_one')
    data['revision'] = data.reference_count-data.estimate
    data['scaled_revision'] = 100*data.revision/data.gross.where(data.gross > 0)
    data['own_relative'] = 100*data.revision/data.reference_count.where(data.reference_count > 0)
    data.loc[data.flow == 'Net migration','own_relative'] = np.nan
    data['reference_age'] = ref
    data['balanced'] = False
    for sample, g in data.groupby('sample'):
        ages = [2,3]+AGES if sample == 'annual_nz' else AGES
        ok = g[g.age.isin(ages)].groupby(['country','period']).revision.agg(['size','count'])
        ok = ok[(ok['size'] == len(ages)*3)&(ok['count'] == len(ages)*3)].reset_index()
        if sample == 'annual_matched':
            both = ok.groupby('period').country.nunique()
            ok = ok[ok.period.isin(both[both == 2].index)]
        keep = set(zip(ok.country,ok.period))
        data.loc[g.index,'balanced'] = [(c,p) in keep for c,p in zip(g.country,g.period)]
    return data

def summary(data, group_columns):
    rows=[]
    for keys,g in data.groupby(group_columns):
        keys = keys if isinstance(keys,tuple) else (keys,)
        x = g.scaled_revision.dropna()
        criterion = g.scaled_revision.abs() <= 2 if g.flow.iloc[0] == 'Net migration' else g.own_relative.abs() <= 5
        rows.append(dict(zip(group_columns,keys),n=len(x),mean_absolute=x.abs().mean(),
            mean_signed=x.mean(),p90_absolute=x.abs().quantile(.9),mean_absolute_persons=g.revision.abs().mean(),
            hits=int(criterion.sum()),attainment=criterion.mean()))
    return pd.DataFrame(rows)

def component_summary(data, groups):
    rows=[]
    for keys,g in data.groupby(groups):
        keys=keys if isinstance(keys,tuple) else (keys,)
        w=g.pivot(index='period',columns='flow',values='scaled_revision').dropna()
        a,d,n=(w[f] for f in FLOWS)
        total=(a*a+d*d).mean();cross=(-2*a*d).mean(); net=(n*n).mean()
        rows.append(dict(zip(groups,keys),n=len(w),arrival_square=(a*a).mean(),departure_square=(d*d).mean(),
                         cross_term=cross,net_square=net,offset_fraction=-cross/total if total else np.nan,
                         rounding_remainder=net-total-cross))
    return pd.DataFrame(rows)

def first_age(summary_table, groups):
    rows=[]
    for keys,g in summary_table.groupby(groups):
        keys=keys if isinstance(keys,tuple) else (keys,)
        rates=g.set_index('age').attainment
        valid=[a for a in rates.index if (rates[rates.index>=a] >= .9).all()]
        rows.append(dict(zip(groups,keys),n=int(g.n.iloc[0]),first_age=min(valid) if valid else np.nan))
    return pd.DataFrame(rows)

def intervals(data):
    d=data[(data['sample']=='annual_nz')&data.balanced].copy()
    assert d.standard_error.notna().all() and (d.standard_error>=0).all()
    d['lower']=d.estimate-1.96*d.standard_error;d['upper']=d.estimate+1.96*d.standard_error
    d['covered']=(d.reference_count>=d.lower)&(d.reference_count<=d.upper)
    d['width']=d.upper-d.lower
    d['score']=interval_score(d.reference_count.to_numpy(),d.lower.to_numpy(),d.upper.to_numpy())
    d['scaled_score']=100*d.score/d.gross;d['scaled_width']=100*d.width/d.gross
    save(d,'annual_interval_periods')
    rows=[]
    for label, g in [('all',d)]+[(ph,d[d.phase==ph]) for ph in PHASES]+[('fully_'+ph,d[(d.phase==ph)&d.fully_contained]) for ph in PHASES]:
        for (flow,age),h in g.groupby(['flow','age']):
            rows.append(dict(group=label,flow=flow,age=age,n=len(h),hits=int(h.covered.sum()),coverage=h.covered.mean(),
                zero_se=int((h.standard_error==0).sum()),mean_width=h.width.mean(),mean_score=h.score.mean(),
                mean_scaled_width=h.scaled_width.mean(),mean_scaled_score=h.scaled_score.mean()))
    save(pd.DataFrame(rows),'annual_interval_summary')
    offsets=[]
    for (flow,age),g in d.groupby(['flow','age']):
        for month,h in g.groupby(g.reference.dt.month):
            offsets.append(dict(flow=flow,age=age,endpoint_month=month,n=len(h),hits=int(h.covered.sum()),coverage=h.covered.mean()))
    save(pd.DataFrame(offsets),'annual_interval_nonoverlap_offsets')
    return d

def phases(original):
    d=original[original.balanced & original.age.isin(AGES)].copy()
    d['phase']=d.reference.map(phase)
    groups=['sample','country','flow','phase','age']
    s=save(summary(d,groups),'phase_profiles_original')
    save(first_age(s,groups[:-1]),'phase_monitoring_original')
    save(component_summary(d,['sample','country','phase','age']),'phase_components_original')
    direction=pd.read_csv(ROOT/'analysis/direction_periods.csv')
    direction=direction[direction.eligible & (direction.deadband_percent==0)].copy()
    direction['phase']=direction.period.map(lambda x:phase(pd.Period(x,freq='Q').to_timestamp('Q')))
    direction['flip']=direction.early_category*direction.reference_category==-1
    save(direction.groupby(['sample','country','phase','age']).agg(n=('flip','size'),flips=('flip','sum'),rate=('flip','mean')).reset_index(),'phase_directions_original')
    monthly=pd.read_csv(ROOT/'analysis/nz_interval_periods.csv',parse_dates=['reference'])
    monthly['phase']=monthly.reference.map(phase)
    save(monthly.groupby(['flow','phase','age']).agg(n=('covered','size'),hits=('covered','sum'),coverage=('covered','mean')).reset_index(),'phase_monthly_intervals')

def run():
    config=json.loads((ROOT/'design/annual-phases-v1.json').read_text())
    source=annual_sources();panel=build_panel(source)
    data=revisions(panel);save(data,'annual_revision_periods')
    good=data[data.balanced & data.age.isin(AGES)]
    groups=['sample','country','flow','age']
    s=save(summary(good,groups),'annual_profiles')
    save(first_age(s,groups[:-1]),'annual_monitoring')
    save(component_summary(good,['sample','country','age']),'annual_components')
    phasesummary=save(summary(good,groups[:-1]+['phase','age']),'phase_profiles_annual')
    save(first_age(phasesummary,groups[:-1]+['phase']),'phase_monitoring_annual')
    save(summary(good[good.fully_contained],groups[:-1]+['phase','age']),'phase_profiles_annual_contained')
    save(component_summary(good,['sample','country','phase','age']),'phase_components_annual')
    save(good[good.flow=='Net migration'][['sample','country','period','phase','fully_contained']+['months_'+p for p in PHASES]].drop_duplicates(),'annual_phase_composition')
    intr=intervals(data)
    orig=pd.read_csv(ROOT/'analysis/revision_periods.csv',parse_dates=['reference'])
    phases(orig)
    # Same-endpoint, same-vintage quarterly versus annual comparison.
    a=good[good['sample']=='annual_matched'].copy()
    q=orig[(orig['sample']=='matched')&orig.balanced&orig.age.isin(AGES)]
    paired=a.merge(q,on=['country','period','age','flow'],suffixes=('_annual','_quarter'),validate='one_to_one')
    assert (paired.vintage_period_annual == paired.vintage_period_quarter).all()
    assert (pd.to_datetime(paired.reference_available_annual) == pd.to_datetime(paired.reference_available_quarter)).all()
    save(paired,'same_endpoint_quarter_annual')
    # Keep every seasonal endpoint offset: selecting only December would hide sensitivity.
    offset_rows=[]
    for (sample,country,flow,age),g in good.groupby(groups):
        for month,h in g.groupby(g.reference.dt.month):
            one=summary(h,groups).iloc[0].to_dict();one['endpoint_month']=int(month)
            offset_rows.append(one)
    offsets=save(pd.DataFrame(offset_rows),'annual_endpoint_profiles')
    save(first_age(offsets,groups[:-1]+['endpoint_month']),'annual_endpoint_monitoring')
    # Reference18/24 comparison uses exactly the same eligible endpoint cohorts.
    later=revisions(panel,24)
    pair=data.merge(later,on=['sample','country','period','flow','age'],suffixes=('_18','_24'),validate='one_to_one')
    pair=pair[pair.balanced_18 & pair.balanced_24 & pair.age.isin(AGES)]
    for ref in [18,24]:
        cols=['sample','country','period','flow','age']
        frame=pair[cols+[c+'_'+str(ref) for c in ['scaled_revision','own_relative','revision']]].copy()
        frame.columns=cols+['scaled_revision','own_relative','revision']
        out=summary(frame,groups);out['reference_age']=ref
        save(out,'annual_reference_'+str(ref))
    save(pair,'annual_reference_pairs')
    ref_intervals=[]
    for (sample,country,flow,age),g in pair[pair['sample']=='annual_nz'].groupby(groups):
        lower=g.estimate_18-1.96*g.standard_error_18;upper=g.estimate_18+1.96*g.standard_error_18
        for ref in [18,24]:
            y=g['reference_count_'+str(ref)];covered=(y>=lower)&(y<=upper)
            ref_intervals.append(dict(flow=flow,age=age,reference_age=ref,n=len(g),hits=int(covered.sum()),coverage=covered.mean()))
    save(pd.DataFrame(ref_intervals),'annual_reference_interval_coverage')
    # Whole-sample sensitivity intervals; no phase-wise significance claims.
    boot=[]
    for keys,g in good.groupby(groups):
        sample,country,flow,age=keys
        grid=sorted(data[data['sample']==sample].period.unique())
        for length in ([12,18,24] if sample=='annual_nz' else [4,6,8]):
            low,high,valid=uncertainty(g.set_index('period').scaled_revision.abs(),grid,length)
            boot.append(dict(sample=sample,country=country,flow=flow,age=age,metric='mean_absolute',block=length,n=len(g),value=g.scaled_revision.abs().mean(),low=low,high=high))
    for (flow,age),g in intr.groupby(['flow','age']):
        grid=sorted(intr.period.unique())
        for length in [12,18,24]:
            low,high,valid=uncertainty(g.set_index('period').covered.astype(float),grid,length)
            boot.append(dict(sample='annual_nz',country='New Zealand',flow=flow,age=age,metric='revision_coverage',block=length,n=len(g),value=g.covered.mean(),low=low,high=high))
    save(pd.DataFrame(boot),'annual_bootstrap')
    excluded=data[(data.age==6)&(data.flow=='Net migration')&~data.balanced][['sample','country','period','missing_reason','reference_count']]
    save(excluded,'annual_exclusions')
    # Metadata inventory binds this extension to the frozen source and prior validated outputs.
    paths=[ROOT/'raw/nz_history.xlsx',ROOT/'analysis/release_calendar.csv',ROOT/'analysis/source_observations.csv',ROOT/'analysis/revision_periods.csv',ROOT/'design/annual-phases-v1.json',Path(__file__)]
    (OUT/'execution.json').write_text(json.dumps({'protocol':config,'sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2))
    print('Annual and phase analyses complete.')

if __name__=='__main__':
    run()

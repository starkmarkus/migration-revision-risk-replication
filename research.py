"""Fixed-age migration vintage panels and descriptive revision analysis."""
from pathlib import Path
import hashlib
import json
import re
from functools import lru_cache
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis'
FLOWS = ['Arrivals', 'Departures', 'Net migration']
AGES = [6, 9, 12, 15]
FREEZE = pd.Timestamp('2026-10-18')
SEED = 20261018
REPS = 10000


def month_end(value):
    return pd.Timestamp(value).to_period('M').to_timestamp('M')


def cutoff(reference, months):
    return month_end(reference) + pd.offsets.MonthEnd(months)


def save(frame, name):
    OUT.mkdir(exist_ok=True)
    frame.to_csv(OUT / (name + '.csv'), index=False)
    return frame


def verify_sources():
    info = json.loads((ROOT/'INPUT_PROVENANCE.json').read_text(encoding='utf-8'))
    rows = []
    for name, expected in info['inputs'].items():
        p = ROOT/name
        actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        rows.append(dict(file=name, expected=expected, actual=actual, matches=actual==expected))
    result = save(pd.DataFrame(rows), 'source_integrity')
    assert result.matches.all(), 'A compact-package input differs from its frozen hash'
    return result


def load_archives():
    manifest = json.loads((ROOT/'results/archive_manifest.json').read_text())
    by_period = {x['period']: x for x in manifest if x['country']=='abs'}
    nz = pd.read_csv(ROOT/'results/nz_vintages.csv')
    nz = nz[nz.frequency=='Monthly'].copy()
    nz['source_reference_date'] = nz.reference
    nz['reference'] = nz.reference.map(month_end)
    save(nz[nz.source_reference_date != nz.reference.dt.strftime('%Y-%m-%d')][['flow','source_reference_date','reference','vintage_period']], 'normalized_month_labels')
    nz['release'] = pd.to_datetime(nz.release)
    nz['country'] = 'New Zealand'
    nz['file'] = 'nz_history.xlsx'
    nz['available'] = nz['release']
    nz['precision'] = 'published_integer'
    nz['official_status'] = 'unknown: no explicit label in consolidated estimate columns'
    au = pd.read_csv(ROOT/'results/abs_vintages.csv')
    au = au[au.precision=='exact_persons'].copy()
    au['reference'] = au.reference.map(month_end)
    catalog = []
    for period, info in by_period.items():
        raw_dates = info.get('release_dates', [])
        parsed = []
        for d in raw_dates:
            try:
                stamp = pd.to_datetime(d, dayfirst=('/' in d), utc=True)
                parsed.append(stamp.tz_convert('Australia/Sydney').tz_localize(None).normalize())
            except (ValueError, TypeError):
                pass
        sub = au[au.vintage_period==period]
        date_match = re.search(r'(\d{1,2} [A-Za-z]{3} \d{4})', sub.release.iloc[0]) if len(sub) else None
        header = pd.to_datetime(date_match.group(1), format='%d %b %Y') if date_match else pd.NaT
        page = min(parsed) if parsed else header
        link_dates = []
        for f in info.get('files', []):
            if len(sub) and f['file']==sub.file.iloc[0]:
                link_dates.extend(pd.to_datetime(s, format='%d.%m.%Y') for s in re.findall(r'\d{2}\.\d{2}\.\d{4}', f['url']))
        link = max(link_dates) if link_dates else pd.NaT
        available = max([d for d in [header, link, page] if not pd.isna(d)]) if not pd.isna(header) else pd.NaT
        catalog.append(dict(country='Australia', vintage_period=period, release=page, header_date=header,
                            archive_link_date=link, available=available, exact_file=sub.file.iloc[0] if len(sub) else '',
                            date_discrepancy=not pd.isna(available) and available!=page, url=info['page_url']))
    # Supplemental 2010Q1 cube is not needed for the declared samples.
    dates = pd.DataFrame(catalog)
    au = au.drop(columns='release').merge(dates[['vintage_period','release','available']], on='vintage_period', validate='many_to_one')
    au['country'] = 'Australia'
    au['standard_error'] = np.nan
    au['official_status'] = 'unknown: label not extracted from detailed cube'
    nzcat = nz[['country','vintage_period','release','available']].drop_duplicates()
    nzcat['exact_file'] = 'nz_history.xlsx'
    nzcat['date_discrepancy'] = False
    dates = pd.concat([dates, nzcat], ignore_index=True).sort_values(['country','release'])
    assert not dates.duplicated(['country','vintage_period']).any()
    save(dates, 'release_calendar')
    raw = pd.concat([nz, au], ignore_index=True)
    assert not raw.duplicated(['country','vintage_period','reference','flow']).any()
    assert raw.estimate.notna().all()
    monthly = nz.copy()
    nq = nz.assign(quarter=nz.reference.dt.to_period('Q'))
    grouped = nq.groupby(['country','vintage_period','quarter','flow'], observed=True)
    quarterly = grouped.agg(estimate=('estimate','sum'), months=('reference','nunique'),
                             release=('release','first'), available=('available','first')).reset_index()
    quarterly = quarterly[quarterly.months==3].copy()
    quarterly['reference'] = quarterly.quarter.dt.to_timestamp('Q').dt.normalize()
    quarterly['standard_error'] = np.nan
    quarterly['file'] = 'nz_history.xlsx'
    quarterly['official_status'] = 'unknown: monthly labels not extracted'
    quarterly['precision'] = 'sum_of_three_published_integers'
    quarterly = pd.concat([quarterly, au], ignore_index=True)
    save(raw, 'source_observations')
    return monthly, quarterly, dates


def build_panels(monthly, quarterly, dates):
    samples = {
        'matched': (quarterly, pd.period_range('2019Q1', '2025Q1', freq='Q'), ['New Zealand','Australia'], AGES),
        'nz_monthly': (monthly, pd.period_range('2019-01','2025-03',freq='M'), ['New Zealand'], [2,3]+AGES),
        'au_extended': (quarterly, pd.period_range('2011Q1','2025Q1',freq='Q'), ['Australia'], AGES),
    }
    panels = []
    for sample, (data, periods, countries, ages) in samples.items():
        for country in countries:
            calendar = dates[(dates.country==country)&(dates.release<=FREEZE)].sort_values('release')
            source = data[data.country==country]
            lookup = {(v,t): x.set_index('flow') for (v,t),x in source.groupby(['vintage_period','reference'])}
            for period in periods:
                end = period.to_timestamp(how='end').normalize()
                for age in ages+[18,24,0]:
                    target = cutoff(end, age) if age else FREEZE
                    if age:
                        eligible = calendar[calendar.release<=min(target, FREEZE)]
                        selected = eligible.iloc[-1] if len(eligible) else None
                    else:
                        first = source[source.reference==end].sort_values('available')
                        selected = calendar[calendar.vintage_period==first.vintage_period.iloc[0]].iloc[0] if len(first) else None
                    reason = ''
                    if target>FREEZE and age:
                        reason = 'cutoff after data freeze'
                    elif selected is None:
                        reason = 'no archived release issued by cutoff'
                    elif pd.isna(selected.available) or selected.available>target:
                        reason = 'latest edition exact file unavailable by cutoff'
                    elif (selected.vintage_period,end) not in lookup:
                        reason = 'reference absent from latest issued edition'
                    value = lookup.get((selected.vintage_period,end)) if not reason else None
                    prior_end = (period-4).to_timestamp(how='end').normalize() if period.freqstr.startswith('Q') else (period-12).to_timestamp(how='end').normalize()
                    prior = lookup.get((selected.vintage_period,prior_end)) if selected is not None and not reason else None
                    for flow in FLOWS:
                        row = value.loc[flow] if value is not None and flow in value.index else None
                        panels.append(dict(sample=sample,country=country,period=str(period),reference=end,age=age,
                            cutoff=target if age else pd.NaT,vintage_period=selected.vintage_period if selected is not None else '',
                            release=selected.release if selected is not None else pd.NaT,
                            available=selected.available if selected is not None else pd.NaT,
                            initial_delay_days=(selected.available-end).days if selected is not None and not pd.isna(selected.available) else np.nan,
                            flow=flow,estimate=row.estimate if row is not None else np.nan,
                            standard_error=row.standard_error if row is not None else np.nan,
                            prior_year=prior.loc[flow,'estimate'] if prior is not None and flow in prior.index else np.nan,
                            official_status=row.official_status if row is not None else 'unavailable',
                            missing_reason=reason if reason else ('' if row is not None else 'flow absent'),
                            file=row.file if row is not None else ''))
    panel = pd.DataFrame(panels)
    assert not panel.duplicated(['sample','country','period','age','flow']).any()
    valid=panel[(panel.age>0)&panel.estimate.notna()]
    assert (valid.available<=valid.cutoff).all()
    assert (valid.release<=valid.cutoff).all()
    save(panel,'asof_panel')
    save(panel.groupby(['sample','country','age','missing_reason'],dropna=False).agg(rows=('estimate','size'),available_rows=('estimate','count')).reset_index(),'panel_availability')
    return panel


def attach_references(panel, reference_age=18):
    key=['sample','country','period','flow']
    target=panel[panel.age==reference_age][key+['estimate','prior_year','vintage_period','available']].rename(columns={
        'estimate':'reference_count','prior_year':'reference_prior_year','vintage_period':'reference_vintage','available':'reference_available'})
    result=panel[panel.age.isin([0,2,3]+AGES)].merge(target,on=key,validate='many_to_one')
    gross=target.pivot(index=['sample','country','period'],columns='flow',values='reference_count').reset_index()
    gross['gross']=gross['Arrivals']+gross['Departures']
    result=result.merge(gross[['sample','country','period','gross']],on=['sample','country','period'],validate='many_to_one')
    current=result.pivot(index=['sample','country','period','age'],columns='flow',values='estimate').reset_index()
    current['current_gross']=current['Arrivals']+current['Departures']
    result=result.merge(current[['sample','country','period','age','current_gross']],on=['sample','country','period','age'],validate='many_to_one')
    result['revision']=result.reference_count-result.estimate
    result['scaled_revision']=100*result.revision/result.gross.where(result.gross>0)
    result['own_relative']=100*result.revision/result.reference_count.where(result.reference_count>0)
    result.loc[result.flow=='Net migration','own_relative']=np.nan
    result['reference_age']=reference_age
    return result


def balanced(data, include_initial=False):
    data=data.copy()
    eligible=[]
    for sample, block in data.groupby('sample'):
        ages=([2,3]+AGES) if sample=='nz_monthly' else AGES
        if include_initial: ages=[0]+ages
        check=block[block.age.isin(ages)].groupby(['country','period']).revision.agg(['size','count'])
        ok=check[(check['size']==len(ages)*3)&(check['count']==len(ages)*3)].reset_index()
        if sample=='matched':
            periods=ok.groupby('period').country.nunique()
            ok=ok[ok.period.isin(periods[periods==2].index)]
        ok['sample']=sample
        eligible.append(ok[['sample','country','period']])
    keep=pd.concat(eligible).assign(balanced=True)
    data=data.merge(keep,on=['sample','country','period'],how='left',validate='many_to_one')
    data['balanced']=data['balanced'].fillna(False).astype(bool)
    return data


@lru_cache(maxsize=80)
def bootstrap_indices(n, block_length, reps=REPS):
    rng=np.random.default_rng(SEED+int(block_length)*10000+n)
    result=np.empty((reps,n),dtype=np.int32)
    result[:,0]=rng.integers(n,size=reps)
    for i in range(1,n):
        restart=rng.random(reps)<1/block_length
        new=rng.integers(n,size=reps)
        result[:,i]=np.where(restart,new,(result[:,i-1]+1)%n)
    return result


def bootstrap_stat(values, indices, operation='mean'):
    sampled=np.asarray(values,float)[indices]
    if operation=='mean':
        count=np.sum(~np.isnan(sampled),axis=1)
        return np.divide(np.nansum(sampled,axis=1),count,out=np.full(len(count),np.nan),where=count>0)
    count=np.sum(~np.isnan(sampled),axis=1)
    ordered=np.sort(sampled,axis=1)
    position=np.maximum(count-1,0)*(.5 if operation=='median' else .9)
    lower=np.floor(position).astype(int);upper=np.ceil(position).astype(int)
    row=np.arange(len(count));weight=position-lower
    value=ordered[row,lower]*(1-weight)+ordered[row,upper]*weight
    return np.where(count>0,value,np.nan)


def uncertainty(values, grid, block_length, operation='mean'):
    array=values.reindex(grid).to_numpy(float)
    dist=bootstrap_stat(array,bootstrap_indices(len(grid),block_length),operation)
    finite=dist[np.isfinite(dist)]
    return (float(np.quantile(finite,.025)),float(np.quantile(finite,.975)),int(len(finite))) if len(finite) else (np.nan,np.nan,0)


def metric_rows(series, grid, block, **labels):
    specifications={
        'mean_signed':(series,'mean'), 'mean_absolute':(series.abs(),'mean'),
        'median_absolute':(series.abs(),'median'), 'p90_absolute':(series.abs(),'p90'),
        'share_up':((series>0).astype(float).where(series.notna()),'mean'),
        'share_down':((series<0).astype(float).where(series.notna()),'mean'),
    }
    rows=[]
    for metric,(values,op) in specifications.items():
        clean=values.dropna()
        point=clean.mean() if op=='mean' else clean.quantile(.5 if op=='median' else .9)
        low,high,nboot=uncertainty(values,grid,block,op)
        rows.append(dict(**labels,metric=metric,n=len(clean),value=point,ci_low=low,ci_high=high,bootstrap_valid=nboot,block_length=block))
    return rows


def revision_profiles(data):
    rows=[]
    for (sample,country,age,flow),g in data.groupby(['sample','country','age','flow']):
        grid=sorted(data[data['sample']==sample].period.unique())
        g=g.set_index('period')
        keep=g.balanced if age!=0 else g.revision.notna()
        block=18 if sample=='nz_monthly' else 6
        for scale,column in [('persons','revision'),('percent_gross','scaled_revision'),('percent_own_flow','own_relative')]:
            if scale=='percent_own_flow' and flow=='Net migration':continue
            rows+=metric_rows(g[column].where(keep),grid,block,sample=sample,country=country,age=age,flow=flow,scale=scale)
    return save(pd.DataFrame(rows),'revision_profiles')


def monitoring(data):
    rows=[];qualifiers=[]
    for (sample,country,flow),g in data[data.age!=0].groupby(['sample','country','flow']):
        ages=sorted(g.age.unique())
        grid=sorted(data[data['sample']==sample].period.unique())
        tolerances=[.5,1,2,5] if flow=='Net migration' else [1,2,5,10]
        column='scaled_revision' if flow=='Net migration' else 'own_relative'
        block=18 if sample=='nz_monthly' else 6
        for tolerance in tolerances:
            rates={}
            for age in ages:
                h=g[(g.age==age)&g.balanced].set_index('period')[column].abs()
                hit=(h<=tolerance).astype(float).where(h.notna())
                low,high,nboot=uncertainty(hit,grid,block)
                rates[age]=hit.mean()
                rows.append(dict(sample=sample,country=country,flow=flow,tolerance=tolerance,age=age,
                                 n=int(hit.count()),hits=int(hit.sum()),attainment=hit.mean(),ci_low=low,ci_high=high,block_length=block))
            for requirement in [.8,.9,.95]:
                qualifies=[age for age in ages if all(rates[a]>=requirement for a in ages if a>=age)]
                qualifiers.append(dict(sample=sample,country=country,flow=flow,tolerance=tolerance,required_attainment=requirement,
                                       first_stable_age=min(qualifies) if qualifies else np.nan,
                                       n=int(g[(g.age==ages[0])&g.balanced][column].count())))
    return save(pd.DataFrame(rows),'monitoring_attainment'),save(pd.DataFrame(qualifiers),'monitoring_first_age')


def direction_stability(data):
    net=data[(data.flow=='Net migration')&(data['sample']!='nz_monthly')&(data.age!=0)].copy()
    net['initial_change']=net.estimate-net.prior_year
    net['reference_change']=net.reference_count-net.reference_prior_year
    rows=[]; transitions=[];detail=[]
    for (sample,country,age),g in net.groupby(['sample','country','age']):
        grid=sorted(data[data['sample']==sample].period.unique())
        g=g.set_index('period')
        valid=g.balanced & g.initial_change.notna() & g.reference_change.notna() & (g.current_gross>0) & (g.gross>0)
        for band in [0,.5,1,2]:
            early=g.initial_change if band==0 else 100*g.initial_change/g.current_gross
            later=g.reference_change if band==0 else 100*g.reference_change/g.gross
            s1=pd.Series(np.where(early>band,1,np.where(early<-band,-1,0)),index=g.index).where(valid)
            s2=pd.Series(np.where(later>band,1,np.where(later<-band,-1,0)),index=g.index).where(valid)
            flip=(s1*s2==-1).astype(float).where(valid)
            change=(s1!=s2).astype(float).where(valid)
            for name,values in [('strict_flip_rate',flip),('category_change_rate',change),
                                 ('flip_given_up',flip.where(s1==1)),('flip_given_down',flip.where(s1==-1))]:
                low,high,nboot=uncertainty(values,grid,6)
                rows.append(dict(sample=sample,country=country,age=age,deadband_percent=band,metric=name,
                                 n=int(values.count()),events=int(values.sum()),value=values.mean(),ci_low=low,ci_high=high,bootstrap_valid=nboot))
            for a in [-1,0,1]:
                for b in [-1,0,1]:
                    transitions.append(dict(sample=sample,country=country,age=age,deadband_percent=band,
                                            early_category=a,reference_category=b,n=int(((s1==a)&(s2==b)).sum())))
            for p in g.index:
                detail.append(dict(sample=sample,country=country,age=age,period=p,deadband_percent=band,eligible=bool(valid[p]),
                                   early_category=s1[p],reference_category=s2[p],early_change=g.loc[p,'initial_change'],reference_change=g.loc[p,'reference_change']))
    save(pd.DataFrame(transitions),'direction_transitions');save(pd.DataFrame(detail),'direction_periods')
    return save(pd.DataFrame(rows),'direction_summary')


def cancellation(data):
    rows=[]; checks=[]
    for (sample,country,age),g in data.groupby(['sample','country','age']):
        grid=sorted(data[data['sample']==sample].period.unique())
        g=g[g.balanced if age else g.revision.notna()]
        for scale,col in [('persons_squared','revision'),('percent_gross_squared','scaled_revision')]:
            wide=g.pivot(index='period',columns='flow',values=col).dropna()
            a,d,n=(wide[c] for c in FLOWS)
            components={'arrival_square':a*a,'departure_square':d*d,'cross_term':-2*a*d,
                        'net_square':n*n,'rounding_remainder':n*n-(a*a+d*d-2*a*d)}
            for name,values in components.items():
                low,high,nboot=uncertainty(values,grid,18 if sample=='nz_monthly' else 6)
                rows.append(dict(sample=sample,country=country,age=age,scale=scale,term=name,n=len(values),value=values.mean(),ci_low=low,ci_high=high))
            for p in wide.index:
                checks.append(dict(sample=sample,country=country,age=age,scale=scale,period=p,
                                   linear_residual=n[p]-a[p]+d[p],squared_remainder=components['rounding_remainder'][p]))
    save(pd.DataFrame(checks),'cancellation_residuals')
    return save(pd.DataFrame(rows),'cancellation')


def interval_score(y, lower, upper, alpha=.05):
    return (upper-lower)+2/alpha*np.maximum(lower-y,0)+2/alpha*np.maximum(y-upper,0)


def interval_usefulness(data):
    g=data[(data['sample']=='nz_monthly')].copy()
    g['lower']=g.estimate-1.96*g.standard_error
    g['upper']=g.estimate+1.96*g.standard_error
    g['covered']=((g.reference_count>=g.lower)&(g.reference_count<=g.upper)).astype(float).where(g.revision.notna()&g.standard_error.notna())
    g['width']=g.upper-g.lower
    g['score']=interval_score(g.reference_count,g.lower,g.upper)
    g['scaled_width']=100*g.width/g.gross
    g['scaled_score']=100*g.score/g.gross
    g['miss_distance']=np.maximum(g.lower-g.reference_count,0)+np.maximum(g.reference_count-g.upper,0)
    save(g,'nz_interval_periods')
    rows=[]
    grid=sorted(g.period.unique())
    for (flow,age),h in g.groupby(['flow','age']):
        h=h.set_index('period')
        valid=h.balanced if age else h.revision.notna()
        for metric in ['covered','width','score','scaled_width','scaled_score']:
            v=h[metric].where(valid)
            low,high,nboot=uncertainty(v,grid,18)
            rows.append(dict(flow=flow,age=age,metric=metric,n=int(v.count()),value=v.mean(),ci_low=low,ci_high=high,
                             hits=int(v.sum()) if metric=='covered' else np.nan,block_length=18))
    save(g[g.miss_distance>0].sort_values('scaled_score',ascending=False),'nz_interval_misses')
    return save(pd.DataFrame(rows),'nz_intervals')


def country_differences(data):
    g=data[(data['sample']=='matched')&data.balanced&(data.age!=0)]
    grid=sorted(data[data['sample']=='matched'].period.unique())
    rows=[]
    for (flow,age),h in g.groupby(['flow','age']):
        for metric in ['signed','absolute','hit']:
            h=h.copy()
            v=h.scaled_revision
            if metric=='absolute':v=v.abs()
            if metric=='hit':
                v=h.scaled_revision if flow=='Net migration' else h.own_relative
                v=(v.abs()<=(2 if flow=='Net migration' else 5)).astype(float)
            h['measure']=v
            p=h.pivot(index='period',columns='country',values='measure')
            diff=p['New Zealand']-p['Australia']
            for block in [4,6,8]:
                low,high,nboot=uncertainty(diff,grid,block)
                rows.append(dict(flow=flow,age=age,metric=metric,n=int(diff.count()),difference_nz_minus_au=diff.mean(),ci_low=low,ci_high=high,block_length=block))
    return save(pd.DataFrame(rows),'paired_country_differences')


def robustness(data, panel, monthly, quarterly, dates):
    rows=[]; age24=balanced(attach_references(panel,24))
    # Identical full-path cohorts under both references.
    keys=['sample','country','period','age','flow']
    both=data.merge(age24[keys+['balanced','revision','scaled_revision','own_relative','reference_count','reference_prior_year']],on=keys,suffixes=('_18','_24'),validate='one_to_one')
    keep=both.balanced_18 & both.balanced_24
    for (sample,country,flow,age),g in both[keep & (both.age!=0)].groupby(['sample','country','flow','age']):
        for ref in [18,24]:
            r=g[f'scaled_revision_{ref}']; e=r if flow=='Net migration' else g[f'own_relative_{ref}']
            rows.append(dict(sample=sample,country=country,flow=flow,age=age,reference_age=ref,n=len(g),
                             mean_absolute_percent_gross=r.abs().mean(),mean_signed_percent_gross=r.mean(),
                             attainment=(e.abs()<=(2 if flow=='Net migration' else 5)).mean(),
                             first_period=min(g.period),last_period=max(g.period)))
    save(pd.DataFrame(rows),'reference_sensitivity')
    save(both[keep], 'reference_sensitivity_periods')
    # Direction eligibility is explicit even where the exact cube history is too short.
    dk=both[keep&(both.age!=0)&(both.flow=='Net migration')&(both['sample']!='nz_monthly')].copy()
    dk['direction_24_eligible']=dk.prior_year.notna()&dk.reference_prior_year_18.notna()&dk.reference_prior_year_24.notna()
    save(dk[['sample','country','period','age','direction_24_eligible']],'direction_24_availability')
    drows=[]
    for (sample,country,age),g in dk[dk.direction_24_eligible].groupby(['sample','country','age']):
        early=g.estimate-g.prior_year
        for ref in [18,24]:
            later=g[f'reference_count_{ref}']-g[f'reference_prior_year_{ref}']
            drows.append(dict(sample=sample,country=country,age=age,reference_age=ref,n=len(g),strict_flip_rate=(early*later<0).mean()))
    save(pd.DataFrame(drows),'direction_reference_sensitivity')
    # Fixed requirement, no tuning: deleting a year changes the denominator only.
    influence=[]; groups=[]; blocks=[];volume=[]
    for (sample,country,flow),g in data[(data.age!=0)&data.balanced].groupby(['sample','country','flow']):
        ages=sorted(g.age.unique());g=g.copy();g['year']=g.reference.dt.year
        column='scaled_revision' if flow=='Net migration' else 'own_relative';tol=2 if flow=='Net migration' else 5
        for yr in sorted(g.year.unique()):
            rates=g[g.year!=yr].groupby('age')[column].apply(lambda v:(v.abs()<=tol).mean())
            eligible=[a for a in ages if all(rates[x]>=.9 for x in ages if x>=a)]
            for age,h in g[(g.year!=yr)].groupby('age'):
                influence.append(dict(sample=sample,country=country,flow=flow,omitted_year=yr,age=age,n=len(h),
                    mean_absolute_percent_gross=h.scaled_revision.abs().mean(),attainment=rates[age],
                    first_stable_age=min(eligible) if eligible else np.nan))
        g['era']=np.where(g.year<2020,'before_2020',np.where(g.year<=2022,'2020_to_2022','2023_onward'))
        for (era,age),h in g.groupby(['era','age']):
            groups.append(dict(sample=sample,country=country,flow=flow,era=era,age=age,n=len(h),
                mean_absolute_percent_gross=h.scaled_revision.abs().mean(),mean_absolute_persons=h.revision.abs().mean(),attainment=(h[column].abs()<=tol).mean()))
        grid=sorted(data[data['sample']==sample].period.unique())
        for age,h in g.groupby('age'):
            h=h.set_index('period')
            for length in ([12,18,24] if sample=='nz_monthly' else [4,6,8]):
                for metric,v in [('mean_absolute_percent_gross',h.scaled_revision.abs()),('attainment',(h[column].abs()<=tol).astype(float))]:
                    low,high,nboot=uncertainty(v,grid,length)
                    blocks.append(dict(sample=sample,country=country,flow=flow,age=age,block_length=length,metric=metric,n=len(h),value=v.mean(),ci_low=low,ci_high=high))
            quartile=pd.qcut(h.gross,4,labels=False,duplicates='drop')+1
            for q in sorted(quartile.dropna().unique()):
                part=h[quartile==q]
                volume.append(dict(sample=sample,country=country,flow=flow,age=age,gross_volume_quartile=q,n=len(part),
                    min_gross=part.gross.min(),max_gross=part.gross.max(),mean_absolute_percent_gross=part.scaled_revision.abs().mean(),
                    mean_absolute_persons=part.revision.abs().mean(),ratio_of_sums_percent=100*part.revision.abs().sum()/part.gross.sum()))
            volume.append(dict(sample=sample,country=country,flow=flow,age=age,gross_volume_quartile=0,n=len(h),min_gross=h.gross.min(),max_gross=h.gross.max(),
                mean_absolute_percent_gross=h.scaled_revision.abs().mean(),mean_absolute_persons=h.revision.abs().mean(),ratio_of_sums_percent=100*h.revision.abs().sum()/h.gross.sum()))
    save(pd.DataFrame(influence),'leave_one_year_out');save(pd.DataFrame(groups),'calendar_era_summary')
    save(pd.DataFrame(blocks),'block_length_sensitivity');save(pd.DataFrame(volume),'volume_sensitivity')
    # Frozen latest NZ counts are available for every monthly cohort; AU cubes have shorter histories.
    corrections=[]
    for sample,source in [('nz_monthly',monthly),('matched',quarterly)]:
        base=data[(data['sample']==sample)&(data.age==6)].copy()
        for country,g in base.groupby('country'):
            s=source[(source.country==country)&(source.available<=FREEZE)]
            latest=s[s.available==s.available.max()]
            merged=g.merge(latest[['reference','flow','estimate','available']],on=['reference','flow'],how='left',suffixes=('','_latest'),validate='one_to_one')
            merged['late_revision']=merged.estimate_latest-merged.reference_count
            merged['late_revision_percent_gross']=100*merged.late_revision/merged.gross
            corrections.append(merged[['sample','country','period','flow','reference_vintage','reference_count','estimate_latest','available_latest','late_revision','late_revision_percent_gross']])
    save(pd.concat(corrections),'latest_vs_18_months')
    # Documented change in NZ training window, by publication rather than reference year.
    nz=data[(data['sample']=='nz_monthly')&data.balanced].copy()
    nz['publication_regime']=np.where(nz.available<pd.Timestamp('2024-08-13'),'before_training_window_change','after_training_window_change')
    regimes=nz.groupby(['flow','age','publication_regime']).agg(n=('revision','count'),mean_signed_percent_gross=('scaled_revision','mean'),
        mean_absolute_percent_gross=('scaled_revision',lambda x:x.abs().mean())).reset_index()
    save(regimes,'nz_publication_regimes')
    return age24


def run():
    verify_sources()
    monthly,quarterly,dates=load_archives()
    panel=build_panels(monthly,quarterly,dates)
    data=balanced(attach_references(panel))
    save(data,'revision_periods')
    audit=data[data.age!=0].groupby(['sample','country','age']).agg(expected_periods=('period','nunique'),available_rows=('revision','count'),balanced_rows=('balanced','sum')).reset_index()
    save(audit,'balanced_cohort_audit')
    results={}
    results['profiles']=revision_profiles(data)
    results['attainment'],results['first_age']=monitoring(data)
    results['direction']=direction_stability(data)
    results['cancellation']=cancellation(data)
    results['intervals']=interval_usefulness(data)
    results['differences']=country_differences(data)
    robustness(data,panel,monthly,quarterly,dates)
    record={'protocol_sha256':hashlib.sha256((ROOT/'design/protocol-v1.json').read_bytes()).hexdigest(),
            'data_freeze':str(FREEZE.date()),'bootstrap_replicates':REPS,'seed':SEED,
            'compact_input_hashes_verified':True,'original_workbook_extraction_rerun':False,'retained_original_workbooks_verified':2,'asof_rows':len(panel),'no_future_releases':True,
            'negative_reference_gross_rows':int((data.gross<=0).sum()),
            'official_status':'unknown unless separately documented; age and zero SE are not official labels'}
    (OUT/'execution.json').write_text(json.dumps(record,indent=2))
    return results


if __name__=='__main__':
    run()
    print('Five analyses and sensitivity tables saved to analysis/.')

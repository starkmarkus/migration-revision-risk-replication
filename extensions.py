"""Prespecified robustness summaries and source-linked revision events."""
import json
import numpy as np
import pandas as pd
from research import OUT, ROOT, FLOWS, AGES, save, uncertainty


def run():
    data=pd.read_csv(OUT/'revision_periods.csv',parse_dates=['reference','available'])
    events=[
        dict(country='New Zealand',event='Person-history linking improvement',timing='July 2019 publications onward',scope='Provisional counts; improved linking of traveller histories',source='raw/nz_history.xlsx',locator='Arrivals note 2'),
        dict(country='New Zealand',event='Additional Customs crossings',timing='May–June 2023',scope='Additional October 2022–March 2023 crossings; some previously final months also corrected',source='raw/nz_history.xlsx',locator='Arrivals notes 10–12'),
        dict(country='New Zealand',event='Training-window change',timing='2024-08-13',scope='32 final months plus finalised crossings in 4 older provisional months',source='https://datainfoplus.stats.govt.nz/item/nz.govt.stats/5e88544a-a7ab-423d-8928-33ae5d346d7a',locator='The training data used in the model; archive note 14'),
        dict(country='New Zealand',event='Cruise passenger-list and journey corrections',timing='June 2026 publication',scope='Final September 2022–November 2024 periods; January 2023 most affected',source='raw/nz_history.xlsx',locator='Arrivals note 15'),
        dict(country='Australia',event='Outgoing passenger card removed; processing improvements',timing='July 2017 onward',scope='Additional movement month and identifier improvements; historical revisions from September 2011',source='https://www.abs.gov.au/methodologies/overseas-migration-methodology/2024-25',locator='2017 – outgoing passenger card removed'),
        dict(country='Australia',event='2018 donor behaviour for initial estimates',timing='2022Q1–2023Q1 reference periods',scope='Exceptional preliminary propensity-model donor period during travel disruption',source='https://www.abs.gov.au/methodologies/overseas-migration-methodology/2024-25',locator='2022 – Impact of COVID-19 travel behaviour'),
        dict(country='Australia',event='Special Purpose visa treatment',timing='December 2024 publication',scope='Removal of incorrectly recorded military movements from September 2021 onward',source='https://www.abs.gov.au/methodologies/overseas-migration-methodology/2024-25',locator='2024 – Revisions for Special Purpose visa holders'),
    ]
    save(pd.DataFrame(events),'event_register')
    # Whole-window actual release delay, keeping the distinction between issue and file dates.
    panel=pd.read_csv(OUT/'asof_panel.csv',parse_dates=['reference','release','available'])
    initial=panel[(panel.age==0)&(panel.flow=='Net migration')].copy()
    initial['headline_delay_days']=(initial.release-initial.reference).dt.days
    save(initial.groupby(['sample','country']).agg(n=('estimate','count'),
        min_exact_delay=('initial_delay_days','min'),median_exact_delay=('initial_delay_days','median'),max_exact_delay=('initial_delay_days','max'),
        median_headline_delay=('headline_delay_days','median')).reset_index(),'initial_release_delays')
    # Available-case profiles retain periods excluded from a balanced path, with the differing N explicit.
    available=[]
    for labels,g in data[data.age>0].groupby(['sample','country','flow','age']):
        sample,country,flow,age=labels;h=g.dropna(subset=['scaled_revision'])
        available.append(dict(sample=sample,country=country,flow=flow,age=age,n=len(h),
            mean_absolute_percent_gross=h.scaled_revision.abs().mean(),mean_signed_percent_gross=h.scaled_revision.mean()))
    save(pd.DataFrame(available),'available_case_profiles')
    # Reapply exactly the same monitoring requirement to the reference sensitivity.
    ref=pd.read_csv(OUT/'reference_sensitivity.csv');rows=[]
    for (sample,country,flow,reference_age),g in ref.groupby(['sample','country','flow','reference_age']):
        rates=g.set_index('age').attainment;ages=sorted(rates.index)
        eligible=[a for a in ages if all(rates[x]>=.9 for x in ages if x>=a)]
        rows.append(dict(sample=sample,country=country,flow=flow,reference_age=reference_age,n=int(g.n.iloc[0]),
            first_stable_age=min(eligible) if eligible else np.nan))
    save(pd.DataFrame(rows),'reference_monitoring_sensitivity')
    # Conditional coverage and influence identify concentration rather than naming a cause.
    intervals=pd.read_csv(OUT/'nz_interval_periods.csv',parse_dates=['reference','available'])
    intervals['year']=intervals.reference.dt.year
    intervals['regime']=np.where(intervals.available<pd.Timestamp('2024-08-13'),'before_training_change','after_training_change')
    yearrows=[];blockrows=[]
    for (flow,age),g in intervals.groupby(['flow','age']):
        for dimension in ['year','regime']:
            for value,h in g.groupby(dimension):
                yearrows.append(dict(flow=flow,age=age,grouping=dimension,group=str(value),n=len(h),hits=int(h.covered.sum()),
                    coverage=h.covered.mean(),mean_width=h.width.mean(),mean_interval_score=h.score.mean(),mean_scaled_score=h.scaled_score.mean()))
        h=g.set_index('period');grid=sorted(intervals.period.unique())
        for block in [12,18,24]:
            for metric in ['covered','width','score','scaled_score']:
                low,high,nboot=uncertainty(h[metric],grid,block)
                blockrows.append(dict(analysis='nz_intervals',sample='nz_monthly',country='New Zealand',flow=flow,age=age,
                                      metric=metric,block_length=block,value=h[metric].mean(),ci_low=low,ci_high=high,n=int(h[metric].count())))
    save(pd.DataFrame(yearrows),'nz_interval_subgroups')
    # Direction and decomposition uncertainty at alternative block lengths.
    direction=pd.read_csv(OUT/'direction_periods.csv')
    for (sample,country,age,band),g in direction.groupby(['sample','country','age','deadband_percent']):
        grid=sorted(data[data['sample']==sample].period.unique());g=g.set_index('period')
        valid=g.eligible;early=g.early_category;later=g.reference_category
        for metric,value in [('strict_flip_rate',(early*later==-1).astype(float)),('category_change_rate',(early!=later).astype(float))]:
            value=value.where(valid)
            for block in [4,6,8]:
                low,high,nboot=uncertainty(value,grid,block)
                blockrows.append(dict(analysis='direction',sample=sample,country=country,flow='Net migration',age=age,
                    metric=metric,deadband_percent=band,block_length=block,value=value.mean(),ci_low=low,ci_high=high,n=int(value.count())))
    for (sample,country,age),g in data[(data.age>0)&data.balanced].groupby(['sample','country','age']):
        grid=sorted(data[data['sample']==sample].period.unique())
        wide=g.pivot(index='period',columns='flow',values='scaled_revision');a,d,n=(wide[f] for f in FLOWS)
        for metric,value in [('cross_term',-2*a*d),('net_square',n*n)]:
            for block in ([12,18,24] if sample=='nz_monthly' else [4,6,8]):
                low,high,nboot=uncertainty(value,grid,block)
                blockrows.append(dict(analysis='cancellation',sample=sample,country=country,flow='Net migration',age=age,
                    metric=metric,block_length=block,value=value.mean(),ci_low=low,ci_high=high,n=int(value.count())))
    save(pd.DataFrame(blockrows),'additional_block_sensitivity')
    # Recorded ABS donor-regime sensitivity: reference-date grouping, not causal comparison.
    au=data[(data.country=='Australia')&data.balanced&(data.age>0)].copy()
    au['donor_regime']=np.where(au.period.between('2022Q1','2023Q1'),'2018_donor_period','other_reference_periods')
    save(au.groupby(['sample','flow','age','donor_regime']).agg(n=('revision','count'),mean_signed_percent_gross=('scaled_revision','mean'),
        mean_absolute_percent_gross=('scaled_revision',lambda x:x.abs().mean())).reset_index(),'au_donor_regimes')
    # Largest interval misses are linked only to documented event windows, not mechanically attributed.
    miss=intervals[intervals.miss_distance>0].sort_values('scaled_score',ascending=False).copy()
    miss['event_context']='No specific correction assigned; see full event register'
    miss.loc[miss.period.between('2020-01','2022-12'),'event_context']='Broad pandemic-era reference window; temporal context only'
    miss.loc[miss.period.between('2022-10','2023-03'),'event_context']='Customs additional-data window (archive note 10); causal share unknown'
    miss.loc[miss.available>=pd.Timestamp('2024-08-13'),'event_context']+='; snapshot after training-window change'
    save(miss,'nz_interval_misses_with_context')
    # Exact pre/post snapshots around the documented 2026 NZ and 2024 ABS events.
    s=pd.read_csv(OUT/'source_observations.csv',parse_dates=['reference','available'])
    cases=[]
    for country,before,after,event in [('New Zealand','2026-03','2026-04','June 2026 correction'),('Australia','2024-03','2024-09','Snapshots bracketing December 2024 treatment')]:
        b=s[(s.country==country)&(s.vintage_period==before)]
        a=s[(s.country==country)&(s.vintage_period==after)]
        pair=b[['reference','flow','estimate','available']].merge(a[['reference','flow','estimate','available']],on=['reference','flow'],suffixes=('_before','_after'),validate='one_to_one')
        pair=pair[pair.reference.map(lambda t:t+pd.offsets.MonthEnd(18))<=pair.available_before].copy()
        pair['country']=country;pair['event']=event;pair['change']=pair.estimate_after-pair.estimate_before
        cases.append(pair)
    save(pd.concat(cases),'documented_late_event_changes')
    return pd.DataFrame(events)

if __name__=='__main__':
    run();print('Robustness extensions complete.')

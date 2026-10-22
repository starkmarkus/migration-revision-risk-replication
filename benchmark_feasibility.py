"""Count-only information-set audit for an annual revision-risk benchmark."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from research import ROOT, FREEZE, cutoff
from annual_phases import PHASES, phase
OUT=ROOT/'analysis'/'benchmark_feasibility'
OUT.mkdir(exist_ok=True)
AGES={'New Zealand':[2,6,9,12,15],'Australia':[6,9,12,15]}
THRESHOLDS={'New Zealand':[12,24,36,60],'Australia':[4,8,12,20]}

def save(frame,name):
    frame.to_csv(OUT/(name+'.csv'),index=False)
    return frame

def nonoverlap(endpoints):
    """Maximum disjoint annual counting windows; NOT independent sample size."""
    months=sorted(set(pd.Timestamp(t).to_period('M').ordinal for t in endpoints))
    selected=[]
    for m in months:
        if not selected or m-selected[-1]>=12:selected.append(m)
    return len(selected)

def extract_metadata():
    # Counts themselves never enter the feasibility decision.
    source=pd.read_csv(ROOT/'analysis/annual_phases/annual_source_values.csv',usecols=['country','reference','vintage_period','available','flow'],parse_dates=['reference','available'])
    calendar=pd.read_csv(ROOT/'analysis/release_calendar.csv',parse_dates=['release','available'])
    groups=source.groupby(['country','vintage_period','reference']).flow.nunique()
    present=set(groups[groups==3].index)
    rows=[]
    for country,ages in AGES.items():
        freq='M' if country=='New Zealand' else 'Q'
        first=source[source.country==country].reference.min().to_period(freq)
        last=pd.Period('2025-03' if freq=='M' else '2025Q1',freq=freq)
        releases=calendar[(calendar.country==country)&(calendar.release<=FREEZE)].sort_values('release')
        for period in pd.period_range(first,last,freq=freq):
            end=period.to_timestamp(how='end').normalize()
            picked={}
            for age in ages+[18]:
                target=cutoff(end,age)
                eligible=releases[releases.release<=min(target,FREEZE)]
                chosen=eligible.iloc[-1] if len(eligible) else None
                reason=''
                if target>FREEZE:reason='cutoff beyond freeze'
                elif chosen is None:reason='no archived release at cutoff'
                elif pd.isna(chosen.available) or chosen.available>target:reason='latest issued exact file unavailable'
                elif (country,chosen.vintage_period,end) not in present:reason='annual total absent in latest issued edition'
                picked[age]=(chosen,target,reason)
            ref,refcut,refreason=picked[18]
            for age in ages:
                early,earlycut,earlyreason=picked[age]
                rows.append(dict(country=country,period=str(period),reference=end,age=age,phase=phase(end),
                    eligible=not (earlyreason or refreason),early_missing=earlyreason,reference_missing=refreason,
                    origin=early.available if early is not None else pd.NaT,nominal_origin=earlycut,
                    early_vintage=early.vintage_period if early is not None else '',
                    reference_vintage=ref.vintage_period if ref is not None else '',
                    reference_file_available=ref.available if ref is not None else pd.NaT,reference_cutoff=refcut,
                    mature_on=max(refcut,ref.available) if ref is not None and not pd.isna(ref.available) else pd.NaT,
                    planned_test=2019<=end.year and end<=pd.Timestamp('2025-03-31')))
    d=pd.DataFrame(rows)
    assert not d.duplicated(['country','period','age']).any()
    valid=d[d.eligible]
    assert (valid.origin<=valid.nominal_origin).all() and (valid.mature_on>=valid.reference_cutoff).all()
    save(d,'archive_eligibility')
    return d

def training_sets(d):
    rows=[];members=[]
    for (country,age),g in d[d.eligible].groupby(['country','age']):
        g=g.sort_values('reference')
        for current in g[g.planned_test].itertuples():
            for policy in ['publication_day','month_end']:
                origin=current.origin if policy=='publication_day' else current.nominal_origin
                available=(g.mature_on<origin) if policy=='publication_day' else (g.mature_on<=origin)
                training=g[available & (g.reference<current.reference)].copy()
                assert not (training.period==current.period).any()
                purged=training[training.reference<=cutoff(current.reference,-12)]
                recent36=training[training.reference>origin-pd.DateOffset(months=36)]
                recent60=training[training.reference>origin-pd.DateOffset(months=60)]
                r=dict(country=country,age=age,period=current.period,reference=current.reference,phase=current.phase,
                    origin_policy=policy,origin=origin,n_train=len(training),n_train_nonoverlap=nonoverlap(training.reference),
                    earliest_training=training.reference.min(),latest_training=training.reference.max(),
                    n_train_purged=len(purged),n_train_purged_nonoverlap=nonoverlap(purged.reference),n_train_recent36=len(recent36),n_train_recent60=len(recent60),
                    n_train_overlap_current=len(training)-len(purged),
                    marginal_tail95=.025*len(training),marginal_tail90=.05*len(training),
                    naive_ref_file_count=int(((g.reference_file_available<origin)&(g.reference<current.reference)).sum()))
                for ph in PHASES:r['train_'+ph]=int((training.phase==ph).sum())
                rows.append(r)
                if policy=='publication_day':
                    for tr in training.itertuples():
                        members.append(dict(country=country,age=age,test_period=current.period,origin=origin,
                            training_period=tr.period,training_reference=tr.reference,training_mature_on=tr.mature_on,
                            training_reference_available=tr.reference_file_available,training_reference_cutoff=tr.reference_cutoff))
    save(pd.DataFrame(members),'training_membership')
    return save(pd.DataFrame(rows),'origin_counts')

def summaries(counts):
    rows=[]
    for (country,age,policy),g in counts.groupby(['country','age','origin_policy']):
        for threshold in THRESHOLDS[country]:
            for mode,col in [('expanding','n_train'),('purged','n_train_purged')]:
                tests=g[g[col]>=threshold].sort_values('reference')
                r=dict(country=country,age=age,origin_policy=policy,training_mode=mode,minimum_train=threshold,
                    tests=len(tests),test_nonoverlap=nonoverlap(tests.reference),first_test=tests.period.iloc[0] if len(tests) else '',
                    last_test=tests.period.iloc[-1] if len(tests) else '',first_origin=tests.origin.min(),last_origin=tests.origin.max(),
                    min_train=tests[col].min(),max_train=tests[col].max(),first_train_nonoverlap=tests['n_train_nonoverlap' if mode=='expanding' else 'n_train_purged_nonoverlap'].iloc[0] if len(tests) else np.nan)
                for ph in PHASES:r['test_'+ph]=int((tests.phase==ph).sum())
                rows.append(r)
    save(pd.DataFrame(rows),'design_options')
    # Start-of-test train/test combinations; no selected outcome or optimized threshold.
    starts=[]
    for (country,age),g in counts[counts.origin_policy=='publication_day'].groupby(['country','age']):
        for year in [2021,2022,2023,2024]:
            tests=g[g.reference>=pd.Timestamp(f'{year}-01-01')].sort_values('reference')
            if not len(tests):continue
            r=tests.iloc[0]
            starts.append(dict(country=country,age=age,start_year=year,first_test=r.period,n_train_first=r.n_train,
                train_nonoverlap_first=r.n_train_nonoverlap,latest_train_first=r.latest_training,tests=len(tests),test_nonoverlap=nonoverlap(tests.reference),
                train_recent36_first=r.n_train_recent36,train_recent60_first=r.n_train_recent60,
                naive_extra_first=r.naive_ref_file_count-r.n_train))
    save(pd.DataFrame(starts),'calendar_start_options')
    # Paired age6 annual comparisons on shared quarter ends; 1/2/3/5 years of native observations.
    paired=[]
    pub=counts[(counts.origin_policy=='publication_day')&(counts.age==6)]
    n=pub[pub.country=='New Zealand'].copy();n=n[n.reference.dt.month.isin([3,6,9,12])]
    a=pub[pub.country=='Australia']
    both=n.merge(a,on='reference',suffixes=('_nz','_au'),validate='one_to_one')
    for years in [1,2,3,5]:
        tests=both[(both.n_train_nz>=12*years)&(both.n_train_au>=4*years)]
        paired.append(dict(nominal_training_years=years,min_nz=12*years,min_au=4*years,tests=len(tests),
            test_nonoverlap=nonoverlap(tests.reference),first_test=tests.reference.min(),last_test=tests.reference.max()))
    save(pd.DataFrame(paired),'paired_country_options')
    save(both,'paired_country_origins')
    # Recent-only feasibility: the maturation delay consumes part of the calendar window.
    # Include other ages, not only paired age6.
    last=counts[counts.origin_policy=='publication_day'].sort_values('reference').groupby(['country','age']).tail(1)
    save(last,'latest_test_training')
    return pd.DataFrame(rows)

def validate(d, counts):
    members=pd.read_csv(OUT/'training_membership.csv',parse_dates=['origin','training_reference','training_mature_on','training_reference_available','training_reference_cutoff'])
    assert (members.training_mature_on<members.origin).all()
    assert (members.training_reference_cutoff<members.origin).all()
    assert (members.training_reference_available<members.origin).all()
    assert not members.duplicated(['country','age','test_period','training_period']).any()
    grouped=members.groupby(['country','age','test_period']).size()
    for r in counts[counts.origin_policy=='publication_day'].itertuples():
        assert grouped.get((r.country,r.age,r.period),0)==r.n_train
    # The max disjoint-window count is independently verified by an interval scheduling DP.
    def dynamic_count(dates):
        v=sorted(set(pd.Timestamp(x).to_period('M').ordinal for x in dates));best=[0]
        for i,x in enumerate(v):
            prior=sum(y<=x-12 for y in v[:i])
            best.append(max(best[-1],1+best[prior]))
        return best[-1]
    for (_,_,_),g in members.groupby(['country','age','test_period']):
        assert dynamic_count(g.training_reference)==nonoverlap(g.training_reference)
    assert nonoverlap(pd.date_range('2020-01-31',periods=12,freq='ME'))==1
    assert nonoverlap(pd.date_range('2020-01-31',periods=13,freq='ME'))==2
    assert pd.Timestamp('2022-05-31')>pd.Timestamp('2025-05-14')-pd.DateOffset(months=36)
    # Reconcile all originally analysed endpoints to the frozen annual panel.
    old=pd.read_csv(ROOT/'analysis/annual_phases/annual_asof_panel.csv',parse_dates=['reference','available'])
    checks=0
    for r in d[d.planned_test & d.eligible].itertuples():
        sample='annual_nz' if r.country=='New Zealand' else 'annual_matched'
        matched=old[(old['sample']==sample)&(old.country==r.country)&(old.reference==r.reference)&(old.age==r.age)&(old.flow=='Net migration')]
        assert len(matched)==1 and pd.notna(matched.estimate.iloc[0])
        assert matched.vintage_period.iloc[0]==r.early_vintage and matched.available.iloc[0]==r.origin
        checks+=1
    rows=[dict(check='All training targets matured before actual forecast publication',n=len(members),passed=True),
          dict(check='Origin counts reconcile to explicit unique training memberships',n=sum(counts.origin_policy=='publication_day'),passed=True),
          dict(check='Disjoint annual-window capacity independently verified by dynamic programming',n=len(grouped),passed=True),
          dict(check='Existing test snapshots reconcile to validated annual panel',n=checks,passed=True)]
    save(pd.DataFrame(rows),'validation_checks')

def run():
    d=extract_metadata();counts=training_sets(d);options=summaries(counts);validate(d,counts)
    files=['analysis/annual_phases/annual_source_values.csv','analysis/release_calendar.csv','design/benchmark-feasibility-v1.json','benchmark_feasibility.py']
    (OUT/'execution.json').write_text(json.dumps({'type':'count-only audit; no benchmark estimated','sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}},indent=2))
    print('Benchmark feasibility audit complete.')
    return counts,options
if __name__=='__main__':run()

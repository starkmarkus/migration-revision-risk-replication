"""Independent annual and phase checks against retained NZ workbooks and frozen ABS extraction."""
from pathlib import Path
import json
import hashlib
import re
import numpy as np
import pandas as pd
import openpyxl
import xlrd
from annual_phases import ROOT, OUT, phase, PHASES


def validate():
    results=[]
    def record(name,n):results.append(dict(check=name,n=int(n),passed=True))
    source=pd.read_csv(OUT/'annual_source_values.csv',parse_dates=['reference'])
    auq=pd.read_csv(ROOT/'analysis/source_observations.csv',parse_dates=['reference'])
    auq=auq[auq.country=='Australia']
    provenance=json.loads((ROOT/'INPUT_PROVENANCE.json').read_text(encoding='utf-8'))
    for name,expected in provenance['inputs'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected
    record('Delivered compact inputs match frozen hashes; omitted originals not checked',len(provenance['inputs']))
    extracted=pd.read_csv(ROOT/'results/abs_vintages.csv')
    extracted=extracted[extracted.precision=='exact_persons'].copy()
    extracted['quarter']=pd.PeriodIndex(extracted.reference,freq='Q')
    keys=['vintage_period','quarter','flow']
    assert not extracted.duplicated(keys).any()
    raw={(r.vintage_period,r.quarter,r.flow):float(r.estimate) for r in extracted.itertuples()}
    for r in source[source.country=='Australia'].itertuples():
        q=r.reference.to_period('Q');total=sum(raw[(r.vintage_period,q-k,r.flow)] for k in range(4))
        assert total==r.estimate
    record('AU annual sums independently recomputed from frozen extracted quarterly input',sum(source.country=='Australia'))
    panel=pd.read_csv(OUT/'annual_asof_panel.csv',parse_dates=['reference','release','available','cutoff'])
    calendar=pd.read_csv(ROOT/'analysis/release_calendar.csv',parse_dates=['release','available'])
    values={(r.country,r.vintage_period,r.reference,r.flow):r.estimate for r in source.itertuples()}
    for r in panel[panel.estimate.notna()].itertuples():
        assert values[(r.country,r.vintage_period,r.reference,r.flow)]==r.estimate
        assert r.available<=r.cutoff and r.release<=r.cutoff
        if r.age:
            latest=calendar[(calendar.country==r.country)&(calendar.release<=r.cutoff)].sort_values('release').iloc[-1]
            assert latest.vintage_period==r.vintage_period
    record('Latest issued annual as-of counts and date gates',panel.estimate.notna().sum())
    intervals=pd.read_csv(OUT/'annual_interval_periods.csv')
    nz=pd.read_csv(ROOT/'results/nz_vintages.csv')
    nz=nz[nz.frequency=='Year ended'].copy();nz['month']=pd.to_datetime(nz.reference).dt.strftime('%Y-%m')
    nzlookup={(r.flow,r.vintage_period,r.month):r for r in nz.itertuples()}
    wb=openpyxl.load_workbook(ROOT/'raw/nz_history.xlsx',read_only=True,data_only=True)
    sheets={s.title:list(s.values) for s in list(wb)[1:]}
    hit=[]
    for r in intervals.itertuples():
        n=nzlookup[(r.flow,r.vintage_period,r.period)];rows=sheets[r.flow];fields=rows[4];start=int(n.source_column)-1
        e=next(i for i in range(start,start+7) if str(fields[i]).startswith('Estimated '));se=next(i for i in range(start,start+7) if fields[i]=='Standard error(1)')
        estimate=rows[int(n.source_row)-1][e];error=rows[int(n.source_row)-1][se]
        refdate=pd.Timestamp(r.reference_available)
        ref=nz[(nz.flow==r.flow)&(nz.month==r.period)&(pd.to_datetime(nz.release)==refdate)].iloc[0]
        rs=next(i for i in range(int(ref.source_column)-1,int(ref.source_column)+6) if str(fields[i]).startswith('Estimated '))
        y=rows[int(ref.source_row)-1][rs]
        lo,hi=estimate-1.96*error,estimate+1.96*error
        assert y==r.reference_count and np.isclose(lo,r.lower) and np.isclose(hi,r.upper)
        covered=lo<=y<=hi;assert covered==r.covered
        score=(hi-lo)+(40*(lo-y) if y<lo else 40*(y-hi) if y>hi else 0)
        assert np.isclose(score,r.score)
        hit.append(covered)
    record('NZ annual interval coverage and scores from raw estimate/SE/reference cells',len(intervals))
    # A second, original release workbook verifies the historical annual columns independently.
    release=openpyxl.load_workbook(ROOT/'raw/nz_2019_06_international-migration-june-2019-.xlsx',read_only=True,data_only=True)
    rawrows=list(release['Table 3'].values);count=0
    for month,rownum in enumerate(range(41,47),1):
        for flow,col in [('Arrivals',3),('Departures',5),('Net migration',7)]:
            n=nzlookup[(flow,'2019-06',f'2019-{month:02}')]
            row=rawrows[rownum-1]
            assert row[col]==n.estimate and row[col+1]==n.standard_error
            count+=1
    record('Original June2019 release annual estimates and SE versus consolidated archive',count)
    d=pd.read_csv(OUT/'annual_revision_periods.csv')
    s=pd.read_csv(OUT/'annual_profiles.csv')
    for r in s.itertuples():
        g=d[(d['sample']==r.sample)&(d.country==r.country)&(d.flow==r.flow)&(d.age==r.age)&d.balanced]
        key=['country','period']
        targ=panel[(panel['sample']==r.sample)&(panel.age==18)]
        gross=targ[targ.flow!='Net migration'].groupby(key).estimate.sum(min_count=2)
        x=np.array([100*(v.reference_count-v.estimate)/gross[(v.country,v.period)] for v in g.itertuples()])
        assert len(x)==r.n and np.isclose(np.abs(x).mean(),r.mean_absolute)
        assert np.isclose(np.mean(x),r.mean_signed)
    record('Annual profile denominators and revisions',len(s))
    for name in ['phase_profiles_original','phase_profiles_annual']:
        frame=pd.read_csv(OUT/(name+'.csv'))
        for keys,g in frame.groupby(['sample','country','flow','age']):
            sample,country,flow,age=keys
            if name.endswith('original'):
                original=pd.read_csv(ROOT/'analysis/revision_periods.csv')
                block=original[(original['sample']==sample)&(original.country==country)&(original.flow==flow)&(original.age==age)&original.balanced]
            else:
                block=d[(d['sample']==sample)&(d.country==country)&(d.flow==flow)&(d.age==age)&d.balanced]
            assert g.n.sum()==len(block)
            assert np.isclose(np.average(g.mean_absolute,weights=g.n),block.scaled_revision.abs().mean())
        record(name+' weighted reconciliation',len(frame))
    # Phase boundaries and 12-month composition distinguish endpoints from exposure.
    assert phase('2019-12-31')==PHASES[0] and phase('2020-01-01')==PHASES[1]
    assert phase('2022-01-01')==PHASES[2] and phase('2023-01-01')==PHASES[3]
    comp=pd.read_csv(OUT/'annual_phase_composition.csv');cols=['months_'+p for p in PHASES]
    assert (comp[cols].sum(axis=1)==12).all()
    assert (comp.fully_contained==(comp[cols].max(axis=1)==12)).all()
    record('Phase composition and boundary checks',len(comp))
    ref=pd.read_csv(OUT/'annual_reference_pairs.csv')
    for c in ['sample','country','flow','age']:
        assert c in ref
    assert ref.balanced_18.all() and ref.balanced_24.all()
    record('Reference sensitivity restricted to identical complete cohorts',len(ref))
    result=pd.DataFrame(results);result.to_csv(OUT/'validation_checks.csv',index=False)
    print(result.to_string(index=False))
    return result

if __name__=='__main__':validate()

"""Reconcile retained NZ source cells, frozen ABS input, panels and exported results."""
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
import openpyxl
import xlrd
from research import ROOT, OUT, FLOWS, AGES


def run():
    checks=[]
    source=pd.read_csv(OUT/'source_observations.csv')
    nz=source[source.country=='New Zealand']
    w=openpyxl.load_workbook(ROOT/'raw/nz_history.xlsx',read_only=True,data_only=True)
    count=0
    for flow,g in nz.groupby('flow'):
        rr=list(w[flow].values)
        starts=[i for i,x in enumerate(rr[3]) if isinstance(x,str) and '(published ' in x]
        specs={}
        for i,start in enumerate(starts):
            end=starts[i+1] if i+1<len(starts) else len(rr[4])
            ec=next(c for c in range(start,end) if isinstance(rr[4][c],str) and rr[4][c].startswith('Estimated '))
            sc=next(c for c in range(start,end) if rr[4][c]=='Standard error(1)')
            specs[start+1]=(ec,sc)
        for row in g.itertuples():
            raw=rr[int(row.source_row)-1];ec,sc=specs[int(row.source_column)]
            assert raw[ec]==row.estimate and raw[sc]==row.standard_error
            assert pd.Timestamp(raw[0]).to_period('M')==pd.Timestamp(row.reference).to_period('M')
            count+=2
    w.close();checks.append(dict(check='NZ estimate and SE cells re-read from workbook',count=count,passed=True))
    au=source[source.country=='Australia'];count=0
    extracted=pd.read_csv(ROOT/'results/abs_vintages.csv')
    extracted=extracted[extracted.precision=='exact_persons']
    keys=['file','sheet','source_row','flow']
    assert not extracted.duplicated(keys).any()
    lookup=extracted.set_index(keys)
    for row in au.itertuples():
        original=lookup.loc[(row.file,row.sheet,row.source_row,row.flow)]
        assert original.estimate==row.estimate
        assert pd.Period(original.reference,freq='M')==pd.Period(row.reference,freq='M')
        count+=1
    checks.append(dict(check='ABS exact counts and month labels versus frozen extracted input; original cells not reread',count=count,passed=True))
    p=pd.read_csv(OUT/'asof_panel.csv',parse_dates=['release','available','cutoff'])
    good=p[(p.age>0)&p.estimate.notna()]
    assert (good.release<=good.cutoff).all() and (good.available<=good.cutoff).all()
    assert not p.duplicated(['sample','country','period','flow','age']).any()
    checks.append(dict(check='Unique as-of keys and no future release/file',count=len(good),passed=True))
    r=pd.read_csv(OUT/'revision_periods.csv');profiles=pd.read_csv(OUT/'revision_profiles.csv');count=0
    for row in profiles.itertuples():
        g=r[(r['sample']==row.sample)&(r.country==row.country)&(r.age==row.age)&(r.flow==row.flow)]
        g=g[g.balanced] if row.age else g
        col={'persons':'revision','percent_gross':'scaled_revision','percent_own_flow':'own_relative'}[row.scale]
        x=g[col].dropna().to_numpy()
        point={'mean_signed':lambda:np.mean(x),'mean_absolute':lambda:np.mean(abs(x)),
               'median_absolute':lambda:np.median(abs(x)),'p90_absolute':lambda:np.quantile(abs(x),.9),
               'share_up':lambda:np.mean(x>0),'share_down':lambda:np.mean(x<0)}[row.metric]()
        assert np.isclose(point,row.value,rtol=1e-10,atol=1e-10)
        assert len(x)==row.n;count+=1
    checks.append(dict(check='Profile metrics recomputed from period revisions',count=count,passed=True))
    att=pd.read_csv(OUT/'monitoring_attainment.csv');first=pd.read_csv(OUT/'monitoring_first_age.csv');count=0
    for row in first.itertuples():
        g=att[(att['sample']==row.sample)&(att.country==row.country)&(att.flow==row.flow)&(att.tolerance==row.tolerance)].sort_values('age')
        passes=g.attainment.to_numpy()>=row.required_attainment
        stable=np.logical_and.accumulate(passes[::-1])[::-1]
        expect=g.age.to_numpy()[stable][0] if stable.any() else np.nan
        assert (np.isnan(expect) and np.isnan(row.first_stable_age)) or expect==row.first_stable_age
        count+=1
    checks.append(dict(check='Persistent monitoring qualification across later ages',count=count,passed=True))
    ip=pd.read_csv(OUT/'nz_interval_periods.csv');summary=pd.read_csv(OUT/'nz_intervals.csv');count=0
    for row in summary[summary.metric=='covered'].itertuples():
        g=ip[(ip.flow==row.flow)&(ip.age==row.age)]
        hit=np.abs(g.reference_count-g.estimate)<=1.96*g.standard_error
        assert int(hit.sum())==row.hits and len(hit)==row.n
        assert np.isclose(hit.mean(),row.value)
        count+=1
    checks.append(dict(check='Interval coverage via independent absolute-distance criterion',count=count,passed=True))
    d=pd.read_csv(OUT/'direction_summary.csv');t=pd.read_csv(OUT/'direction_transitions.csv');count=0
    for row in d[d.metric=='strict_flip_rate'].itertuples():
        g=t[(t['sample']==row.sample)&(t.country==row.country)&(t.age==row.age)&(t.deadband_percent==row.deadband_percent)]
        assert g.n.sum()==row.n
        assert g[g.early_category*g.reference_category==-1].n.sum()==row.events
        count+=1
    checks.append(dict(check='Direction reversals match transition matrices',count=count,passed=True))
    decomp=pd.read_csv(OUT/'cancellation.csv');count=0
    for _,g in decomp.groupby(['sample','country','age','scale']):
        a=g.set_index('term').value
        expect=a.arrival_square+a.departure_square+a.cross_term+a.rounding_remainder
        assert np.isclose(expect,a.net_square,atol=1e-7,rtol=1e-10);count+=1
    checks.append(dict(check='Squared decomposition including retained rounding remainder',count=count,passed=True))
    # Same reference-age sensitivity cohort and exact documented late correction.
    s=pd.read_csv(OUT/'reference_sensitivity.csv')
    for _,g in s.groupby(['sample','country','flow','age']):
        assert g.n.nunique()==1 and g.first_period.nunique()==1 and g.last_period.nunique()==1
    c=pd.read_csv(OUT/'documented_late_event_changes.csv')
    case=c[(c.country=='New Zealand')&(c.reference=='2023-01-31')].set_index('flow').change
    assert case.Arrivals==-1884 and case.Departures==-138 and case['Net migration']==-1746
    checks.append(dict(check='Reference cohorts matched; January 2023 correction matches source note',count=3,passed=True))
    out=pd.DataFrame(checks);out.to_csv(OUT/'validation_checks.csv',index=False)
    return out

if __name__=='__main__':
    print(run().to_string(index=False))

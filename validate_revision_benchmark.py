"""Independent numerical and temporal checks for the single revision benchmark."""
import json
import math
import hashlib
import numpy as np
import pandas as pd
from research import ROOT, verify_sources
import revision_benchmark as b


def linear_quantile(values,p):
    ordered=sorted(values)
    position=(len(ordered)-1)*p
    k=math.floor(position)
    return ordered[k]+(position-k)*(ordered[min(k+1,len(ordered)-1)]-ordered[k])


def run():
    checks=[]
    def passed(name,n): checks.append(dict(check=name,n=int(n),passed=True))
    integrity=verify_sources()
    passed('Frozen compact inputs match distribution checksums; omitted originals not checked',len(integrity))
    data=b.prepare()
    p=pd.read_csv(b.OUT/'predictions.csv',parse_dates=['reference','origin','last_mature_on'])
    members=pd.read_csv(b.OUT/'training_membership.csv',parse_dates=['origin','training_mature_on','training_reference'])
    oldcounts=pd.read_csv(ROOT/'analysis/benchmark_feasibility/origin_counts.csv')
    oldcounts=oldcounts[(oldcounts.age==6)&(oldcounts.origin_policy=='publication_day')].set_index(['country','period'])
    oldmembers=pd.read_csv(ROOT/'analysis/benchmark_feasibility/training_membership.csv')
    oldmembers=oldmembers[oldmembers.age==6]
    assert not p.duplicated(['country','flow','period','method']).any()
    for r in p[p.method=='Empirical revision'].itertuples():
        tr=data[(data.country==r.country)&(data.flow==r.flow)&(data.mature_on<r.origin)&(data.reference<r.reference)]
        m=members[(members.country==r.country)&(members.flow==r.flow)&(members.test_period==r.period)]
        prior=oldmembers[(oldmembers.country==r.country)&(oldmembers.test_period==r.period)]
        assert len(tr)==r.n_train==oldcounts.loc[(r.country,r.period),'n_train']
        assert set(tr.period)==set(m.training_period)==set(prior.training_period)
        assert (tr.reference<=r.reference-pd.DateOffset(months=12)).all()
        values=(tr.target-tr.estimate)/tr.early_gross
        lo=r.estimate+r.early_gross*linear_quantile(values,.025)
        hi=r.estimate+r.early_gross*linear_quantile(values,.975)
        np.testing.assert_allclose([r.lower,r.upper],[lo,hi],rtol=1e-12,atol=1e-8)
    passed('Every forecast matches independently interpolated training quantiles',sum(p.method=='Empirical revision'))
    passed('Training membership/counts agree with the preceding count-only audit',sum(p.method=='Empirical revision'))
    assert (members.training_mature_on<members.origin).all()
    passed('All included reference targets mature strictly before publication',len(members))
    for r in p.itertuples():
        expected=r.upper-r.lower
        if r.target<r.lower:expected+=40*(r.lower-r.target)
        elif r.target>r.upper:expected+=40*(r.target-r.upper)
        assert math.isclose(r.score,expected,rel_tol=1e-12,abs_tol=1e-7)
        assert r.covered==(r.lower<=r.target<=r.upper)
        assert r.miss_below==(r.target<r.lower) and r.miss_above==(r.target>r.upper)
        assert math.isclose(r.scaled_score,100*expected/r.early_gross,rel_tol=1e-12,abs_tol=1e-9)
    passed('Independent piecewise interval scores, hits and early-gross scales',len(p))
    old=pd.read_csv(ROOT/'analysis/annual_phases/annual_interval_periods.csv',parse_dates=['reference'])
    old=old[(old['sample']=='annual_nz')&(old.age==6)].set_index(['flow','reference'])
    for r in p[p.method=='Published model'].itertuples():
        baseline=old.loc[(r.flow,r.reference)]
        np.testing.assert_allclose([r.lower,r.upper,r.width,r.score,r.target],
                                  [baseline.lower,baseline.upper,baseline.width,baseline.score,baseline.reference_count],rtol=1e-11,atol=1e-7)
    passed('NZ baseline agrees with previously validated published annual intervals',sum(p.method=='Published model'))
    for country,n in [('New Zealand',33),('Australia',24)]:
        for flow in b.FLOWS:
            assert len(p[(p.country==country)&(p.flow==flow)&(p.method=='Empirical revision')])==n
    for _,sample in b.samples(p):
        if _=='Shared quarter ends':
            assert (sample.groupby(['country','flow','method']).size()==11).all()
    passed('Native and shared-endpoint sample sizes match feasibility audit',9)
    # Change all current/future unavailable outcomes; bounds at the first test must be identical.
    config=json.loads(b.PROTOCOL.read_text())
    for country in ['New Zealand','Australia']:
        first=p[(p.country==country)&(p.flow=='Net migration')&(p.method=='Empirical revision')].sort_values('reference').iloc[0]
        altered=data.copy()
        unavailable=(altered.country==country)&(altered.mature_on>=first.origin)
        altered.loc[unavailable,'target']+=1234567
        altered.loc[unavailable,'scaled_signed_revision']=(altered.loc[unavailable,'target']-altered.loc[unavailable,'estimate'])/altered.loc[unavailable,'early_gross']
        changed,_=b.fit(altered,config)
        one=changed[(changed.country==country)&(changed.flow=='Net migration')&(changed.period==first.period)&(changed.method=='Empirical revision')].iloc[0]
        np.testing.assert_allclose(one[['lower','upper']].to_numpy(float),first[['lower','upper']].to_numpy(float),rtol=0,atol=1e-8)
    passed('Perturbing all unavailable targets leaves first-test interval bounds unchanged',2)
    summary=pd.read_csv(b.OUT/'summary.csv')
    for name,g in b.samples(p):
        for keys,rows in g.groupby(['country','flow','method']):
            s=summary[(summary['sample']==name)&(summary.country==keys[0])&(summary.flow==keys[1])&(summary.method==keys[2])].iloc[0]
            assert s.n==len(rows) and s.hits==sum(rows.covered)
            np.testing.assert_allclose([s.mean_width,s.mean_score],[sum(rows.upper-rows.lower)/len(rows),sum(rows.score)/len(rows)],rtol=1e-12)
    passed('All summary cells reconcile with forecast-level outputs',len(summary))
    pd.DataFrame(checks).to_csv(b.OUT/'validation_checks.csv',index=False)
    (b.OUT/'validation_execution.json').write_text(json.dumps({'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':checks},indent=2))
    return pd.DataFrame(checks)

from pathlib import Path
if __name__=='__main__': print(run().to_string(index=False))

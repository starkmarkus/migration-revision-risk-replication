"""One expanding empirical interval for six-month annual migration revisions."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from research import ROOT, FLOWS
from benchmark_feasibility import nonoverlap

OUT = ROOT / 'analysis/revision_benchmark'
PROTOCOL = ROOT / 'design/revision-benchmark-v1.json'


def prepare():
    meta = pd.read_csv(ROOT/'analysis/benchmark_feasibility/archive_eligibility.csv',
                       parse_dates=['reference','origin','nominal_origin','reference_file_available','reference_cutoff','mature_on'])
    meta = meta[(meta.age == 6) & meta.eligible].copy()
    source = pd.read_csv(ROOT/'analysis/annual_phases/annual_source_values.csv',
                         parse_dates=['reference','available'])
    idx = source.set_index(['country','reference','vintage_period','flow'])
    assert idx.index.is_unique
    rows = []
    for r in meta.to_dict('records'):
        early = {f: idx.loc[(r['country'],r['reference'],r['early_vintage'],f)] for f in FLOWS}
        target = {f: idx.loc[(r['country'],r['reference'],r['reference_vintage'],f)] for f in FLOWS}
        gross = early['Arrivals'].estimate + early['Departures'].estimate
        assert gross > 0
        for f in FLOWS:
            assert early[f].available == r['origin']
            assert target[f].available == r['reference_file_available']
            rows.append(dict(**r,flow=f,estimate=early[f].estimate,
                standard_error=early[f].standard_error,target=target[f].estimate,
                early_gross=gross,scaled_signed_revision=(target[f].estimate-early[f].estimate)/gross,
                early_file=early[f].file,reference_file=target[f].file))
    data = pd.DataFrame(rows)
    assert not data.duplicated(['country','flow','period']).any()
    return data


def predict(training_revisions, estimate, early_gross):
    """Only matured normalized revisions and current published counts enter bounds."""
    q = np.quantile(np.asarray(training_revisions), [.025,.975], method='linear')
    return estimate + early_gross*q, q


def score(target, lower, upper):
    return upper-lower + 40*np.maximum(lower-target,0) + 40*np.maximum(target-upper,0)


def fit(data, config):
    predictions=[];members=[]
    for (country,flow),g in data.groupby(['country','flow']):
        g=g.sort_values('reference')
        for r in g[g.planned_test].itertuples():
            training=g[(g.mature_on<r.origin)&(g.reference<r.reference)]
            if len(training)<config['warmup'][country]:
                continue
            bounds,q=predict(training.scaled_signed_revision,r.estimate,r.early_gross)
            base=dict(country=country,flow=flow,period=r.period,reference=r.reference,
                phase=r.phase,origin=r.origin,early_vintage=r.early_vintage,reference_vintage=r.reference_vintage,
                estimate=r.estimate,target=r.target,standard_error=r.standard_error,early_gross=r.early_gross,
                n_train=len(training),first_train=training.reference.min(),last_train=training.reference.max(),
                last_mature_on=training.mature_on.max(),train_disjoint_windows=nonoverlap(training.reference))
            intervals=[('Empirical revision',bounds)]
            if country=='New Zealand':
                assert np.isfinite(r.standard_error) and r.standard_error>=0
                intervals.append(('Published model',np.array([r.estimate-1.96*r.standard_error,r.estimate+1.96*r.standard_error])))
            for method,(lower,upper) in intervals:
                predictions.append(dict(**base,method=method,lower=lower,upper=upper,
                    quantile_lower=q[0] if method=='Empirical revision' else np.nan,
                    quantile_upper=q[1] if method=='Empirical revision' else np.nan,
                    covered=lower<=r.target<=upper,miss_below=r.target<lower,miss_above=r.target>upper,
                    width=upper-lower,score=score(r.target,lower,upper),
                    scaled_width=100*(upper-lower)/r.early_gross,
                    scaled_score=100*score(r.target,lower,upper)/r.early_gross))
            for t in training.itertuples():
                members.append(dict(country=country,flow=flow,test_period=r.period,origin=r.origin,
                    training_period=t.period,training_reference=t.reference,training_mature_on=t.mature_on,
                    early_gross=t.early_gross,estimate=t.estimate,target=t.target,
                    scaled_signed_revision=t.scaled_signed_revision))
    return pd.DataFrame(predictions),pd.DataFrame(members)


def samples(predictions):
    nz=set(predictions.loc[(predictions.country=='New Zealand') & predictions.reference.dt.month.isin([3,6,9,12]),'reference'])
    au=set(predictions.loc[predictions.country=='Australia','reference'])
    common=nz&au
    yield 'Native cadence',predictions
    yield 'Shared quarter ends',predictions[predictions.reference.isin(common)]


def summaries(predictions):
    totals=[];phases=[];years=[];paired=[]
    def row(key,g):
        return dict(**key,n=len(g),first=g.reference.min(),last=g.reference.max(),
            disjoint_windows=nonoverlap(g.reference),hits=int(g.covered.sum()),coverage_pct=100*g.covered.mean(),
            misses_below=int(g.miss_below.sum()),misses_above=int(g.miss_above.sum()),
            mean_width=g.width.mean(),mean_score=g.score.mean(),
            mean_scaled_width=g.scaled_width.mean(),mean_scaled_score=g.scaled_score.mean(),
            min_train=int(g.n_train.min()),max_train=int(g.n_train.max()))
    for sample,p in samples(predictions):
        keys=['country','flow','method']
        for k,g in p.groupby(keys):
            totals.append(row(dict(sample=sample,**dict(zip(keys,k))),g))
        for k,g in p.groupby(keys+['phase']):
            phases.append(row(dict(sample=sample,**dict(zip(keys+['phase'],k))),g))
        for k,g in p.assign(year=p.reference.dt.year).groupby(keys+['year']):
            years.append(row(dict(sample=sample,**dict(zip(keys+['year'],k))),g))
        nz=p[p.country=='New Zealand']
        for flow,g in nz.groupby('flow'):
            b=g[g.method=='Empirical revision'].set_index('period')
            o=g[g.method=='Published model'].set_index('period').loc[b.index]
            assert np.array_equal(b.target,o.target)
            paired.append(dict(sample=sample,flow=flow,n=len(b),
                coverage_gain_pp=100*(b.covered.mean()-o.covered.mean()),
                width_ratio=b.width.mean()/o.width.mean(),
                score_change=b.score.mean()-o.score.mean(),
                score_reduction_pct=100*(1-b.score.mean()/o.score.mean()),
                scaled_score_reduction_pct=100*(1-b.scaled_score.mean()/o.scaled_score.mean()),
                benchmark_better=int((b.score<o.score).sum()),official_better=int((b.score>o.score).sum()),
                ties=int(np.isclose(b.score,o.score,rtol=0,atol=1e-8).sum())))
    for name,rows in [('summary',totals),('by_phase',phases),('by_year',years),('paired_comparison',paired)]:
        pd.DataFrame(rows).to_csv(OUT/(name+'.csv'),index=False)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    config=json.loads(PROTOCOL.read_text())
    data=prepare()
    p,m=fit(data,config)
    data.to_csv(OUT/'eligible_revisions.csv',index=False)
    p.to_csv(OUT/'predictions.csv',index=False)
    m.to_csv(OUT/'training_membership.csv',index=False)
    summaries(p)
    files=['revision_benchmark.py','design/revision-benchmark-v1.json',
        'analysis/benchmark_feasibility/archive_eligibility.csv',
        'analysis/annual_phases/annual_source_values.csv']
    (OUT/'execution.json').write_text(json.dumps(dict(protocol=config,sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}),indent=2))
    return p,m

if __name__=='__main__':
    run()
    print(pd.read_csv(OUT/'summary.csv').to_string(index=False))
    print(pd.read_csv(OUT/'paired_comparison.csv').to_string(index=False))

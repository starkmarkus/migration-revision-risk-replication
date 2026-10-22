"""Independently validate new sensitivity against as-of counts using Decimal."""
from pathlib import Path
from decimal import Decimal
import csv
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/denominator_sensitivity'
def rows(path):
    with (ROOT/path).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

panels = {}
for typ, path in [('quarterly','analysis/asof_panel.csv'), ('annual','analysis/annual_phases/annual_asof_panel.csv')]:
    panels[typ] = {(r['sample'], r['country'], r['period'], int(r['age']), r['flow']): r for r in rows(path)}
expected = {}
checked = 0
for r in rows('analysis/denominator_sensitivity/observations.csv'):
    p = panels['quarterly' if r['sample']=='matched' else 'annual']
    prefix = (r['sample'], r['country'], r['period'])
    age = int(r['age'])
    early = {f: p[prefix+(age,f)] for f in ['Arrivals','Departures','Net migration']}
    later = {f: p[prefix+(18,f)] for f in ['Arrivals','Departures','Net migration']}
    assert len({v['vintage_period'] for v in early.values()}) == 1
    delta = abs(Decimal(later['Net migration']['estimate'])-Decimal(early['Net migration']['estimate']))
    for denominator, selected in [('reference_gross',later),('contemporaneous_gross',early)]:
        gross = Decimal(selected['Arrivals']['estimate'])+Decimal(selected['Departures']['estimate'])
        assert gross > 0 and gross == Decimal(r[denominator])
        hit = delta <= Decimal('.02')*gross
        assert hit == (r[denominator+'_hit']=='True')
        key = (r['cohort'], denominator, age)
        expected.setdefault(key, []).append(hit)
        checked += 1
for r in rows('analysis/denominator_sensitivity/attainment.csv'):
    v = expected[(r['cohort'],r['denominator'],int(r['age']))]
    assert sum(v)==int(r['hits']) and len(v)==int(r['n'])
for r in rows('analysis/denominator_sensitivity/horizons.csv'):
    ages = [6,9,12,15]
    qualifies = {}
    for age in ages:
        v = expected[(r['cohort'],r['denominator'],age)]
        qualifies[age] = 10*sum(v) >= 9*len(v)
    horizon = next((a for a in ages if all(qualifies[b] for b in ages if b>=a)),None)
    assert horizon == int(r['first_age'])
(OUT/'validation.json').write_text(json.dumps({
    'method':'Decimal arithmetic from original extracted as-of component and net counts; independent of generator',
    'observation_denominator_checks':checked, 'attainment_cells':len(expected),
    'horizons':10, 'passed':True
},indent=2),encoding='utf-8')
print('Validated denominator sensitivity:',checked,'observation/denominator pairs and 10 horizons.')

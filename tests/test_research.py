import unittest
import numpy as np
import pandas as pd
import research as r


class ResearchTests(unittest.TestCase):
    def test_calendar_month_end(self):
        self.assertEqual(r.cutoff('2020-02-29', 18), pd.Timestamp('2021-08-31'))
        self.assertEqual(r.cutoff('2019-03-31', 6), pd.Timestamp('2019-09-30'))
        self.assertEqual(r.month_end('2021-10-30'),pd.Timestamp('2021-10-31'))

    def test_interval_score(self):
        y=np.array([5,0,12]);lo=np.array([2,2,2]);hi=np.array([10,10,10])
        np.testing.assert_array_equal(r.interval_score(y,lo,hi),[8,88,88])

    def test_block_resampling_paths(self):
        a=r.bootstrap_indices(25,6)
        self.assertEqual(a.shape,(10000,25))
        np.testing.assert_array_equal(a,r.bootstrap_indices(25,6))
        self.assertTrue(((a>=0)&(a<25)).all())
        continuations=(a[:,1:]==(a[:,:-1]+1)%25).mean()
        self.assertTrue(.82<continuations<.86)
        # Joint resampling preserves any exact cross-country path relationship.
        x=np.arange(25.); y=x+10
        np.testing.assert_allclose(y[a]-x[a],10)

    def test_missing_value_quantiles(self):
        values=np.array([1.,2.,np.nan,8.,13.])
        indices=r.bootstrap_indices(5,2,100)
        for operation,quantile in [('median',.5),('p90',.9)]:
            np.testing.assert_allclose(r.bootstrap_stat(values,indices,operation),
                                       np.nanquantile(values[indices],quantile,axis=1),equal_nan=True)

    def test_rounded_net_identity(self):
        a=np.array([5.,-2]);d=np.array([3.,4]);n=np.array([2.,-5])
        residual=n*n-(a*a+d*d-2*a*d)
        np.testing.assert_allclose(residual,[0,-11])

    def test_source_and_asof_gate(self):
        m,q,d=r.load_archives();p=r.build_panels(m,q,d)
        miss=p[(p['sample']=='matched')&(p.country=='Australia')&(p.period=='2019Q1')&(p.age==6)]
        self.assertTrue(miss.estimate.isna().all())
        nz=p[(p['sample']=='nz_monthly')&(p.period=='2021-10')&(p.age==6)]
        self.assertEqual(nz.estimate.count(),3)
        good=p[(p.age>0)&p.estimate.notna()]
        self.assertTrue((good.available<=good.cutoff).all())
        # NZ quarter counts must come from three months in exactly one vintage.
        one=p[(p['sample']=='matched')&(p.country=='New Zealand')&(p.period=='2023Q1')&(p.age==6)&(p.flow=='Arrivals')].iloc[0]
        subset=m[(m.vintage_period==one.vintage_period)&(m.reference.dt.to_period('Q')==pd.Period('2023Q1'))&(m.flow=='Arrivals')]
        self.assertEqual(len(subset),3)
        self.assertEqual(one.estimate,subset.estimate.sum())
        self.assertTrue(np.isnan(one.standard_error))

if __name__=='__main__':unittest.main()

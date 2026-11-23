"""Computational checks only. Synthetic data are not empirical COSE results."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_cluster, cov_cluster_2groups

sys.path.insert(0,str(Path(__file__).resolve().parent/"cloud"))
from cose_core import (BAN, Design, Injection, event_window, load_panel, subset_panel,
    window_audit, floor_brackets, wilson, bootstrap_log_outcome, SCENARIOS)
from run_analysis import label_seed


def synthetic(missing=False, beta=.35, seed=173):
    rng=np.random.default_rng(seed); rows=[]
    dates=pd.date_range(BAN-pd.Timedelta(days=21),BAN+pd.Timedelta(days=21),freq="D")
    for i in range(20):
        for j,date in enumerate(dates):
            if missing and rng.random()<.13: continue
            tr=i<10
            y=2+.05*i+.2*np.sin(j/3)+beta*(tr and date>=BAN)+rng.normal(0,.12)
            rows.append({"item":f"item_{i:02}","arm":"candidate" if tr else "control",
                         "day":date,"units":np.expm1(y),"vwap":5.})
    return pd.DataFrame(rows).sort_values(["day","item"]).reset_index(drop=True)


def explicit(design):
    d=design.d
    ent=pd.get_dummies(d.item,drop_first=False,dtype=float).to_numpy()
    if design.model=="item_post":
        x=np.column_stack([ent,design.post,design.x])
    else:
        dt=pd.get_dummies(d.day,drop_first=True,dtype=float).to_numpy()
        x=np.column_stack([ent,dt,design.x])
    return sm.OLS(np.log1p(d.units.to_numpy()),x).fit()


class TestRebuild(unittest.TestCase):
    def check_ols(self,model,missing):
        design=Design(synthetic(missing),BAN,model); got=design.fit(); ref=explicit(design)
        self.assertAlmostEqual(got["coefficient"],ref.params[-1],places=10)
        np.testing.assert_allclose(got["residual"],ref.resid,atol=2e-9)
        self.assertAlmostEqual(got["se_item"],np.sqrt(cov_cluster(ref,design.ii)[-1,-1]),places=9)
        self.assertAlmostEqual(got["se_date"],np.sqrt(cov_cluster(ref,design.tt)[-1,-1]),places=9)
        v2=cov_cluster_2groups(ref,design.ii,design.tt)[0][-1,-1]
        if v2>=0: self.assertAlmostEqual(got["se_item_date"],np.sqrt(v2),places=9)
        else: self.assertTrue(got["two_way_variance_negative"])

    def test_item_post_balanced(self): self.check_ols("item_post",False)
    def test_item_post_unbalanced(self): self.check_ols("item_post",True)
    def test_twfe_balanced(self): self.check_ols("twfe",False)
    def test_twfe_unbalanced(self): self.check_ols("twfe",True)

    def test_balanced_coefficients_agree(self):
        d=synthetic(); a=Design(d,BAN,"item_post").fit(); b=Design(d,BAN,"twfe").fit()
        self.assertAlmostEqual(a["coefficient"],b["coefficient"],places=10)

    def test_known_effect_exact(self):
        d=synthetic(); i=pd.factorize(d.item)[0]; t=((d.day-d.day.min())/pd.Timedelta(days=1)).to_numpy()
        treat=d.arm.eq("candidate").to_numpy(); post=(d.day>=BAN).to_numpy()
        y=3+i*.01+np.sin(t/2)*.1+.42*treat*post
        d["units"]=np.expm1(y)
        self.assertAlmostEqual(Design(d,BAN,"twfe").fit()["coefficient"],.42,places=10)

    def test_window_endpoints(self):
        a=window_audit(synthetic(),BAN,"legacy21"); b=window_audit(synthetic(),BAN,"tight21")
        self.assertEqual(str(a["end"].date()),"2019-11-18")
        self.assertEqual(a["nominal_post_days"],22)
        self.assertEqual(str(b["end"].date()),"2019-11-17")
        self.assertEqual(b["nominal_post_days"],21)

    def test_cached_injection_matches_full_refits(self):
        for model in ("item_post","twfe"):
            z=event_window(synthetic(True),BAN,"tight21"); design=Design(z,BAN,model)
            inj=Injection(design,"tight21"); y=np.log1p(z.units.to_numpy()); grid=np.array([0,3,30,44,100.])
            w,_=inj.weights("heterogeneous",np.random.default_rng(12),"equal_total")
            cached=inj.beta_path(y,w,grid)
            for j,g in enumerate(grid):
                new=z.copy(); u=new.units.to_numpy().copy(); u[inj.target]+=inj.base*w*g/100; new["units"]=u
                ref=Design(new,BAN,model).fit()["coefficient"]
                self.assertAlmostEqual(cached[j],ref,places=10)

    def test_zero_injection_identical(self):
        des=Design(event_window(synthetic(),BAN,"tight21"),BAN,"item_post"); inj=Injection(des,"tight21")
        y=np.log1p(des.d.units.to_numpy()); w,_=inj.weights("distributed",np.random.default_rng(3))
        self.assertEqual(inj.beta_path(y,w,np.array([0.]))[0],des.beta(y))

    def test_abrupt_total_conserved_balanced(self):
        des=Design(event_window(synthetic(),BAN,"tight21"),BAN,"item_post"); inj=Injection(des,"tight21")
        w,detail=inj.weights("abrupt",np.random.default_rng(0))
        self.assertAlmostEqual(w.sum(),1.,places=12)
        self.assertAlmostEqual(detail["lost_to_unobserved_cells_fraction"],0.,places=12)
        self.assertTrue(np.all(des.treat[inj.target]==1)); self.assertTrue(np.all(des.post[inj.target]==1))

    def test_missing_cells_not_filled(self):
        des=Design(event_window(synthetic(True),BAN,"tight21"),BAN,"item_post"); inj=Injection(des,"tight21")
        n=len(des.d); w,detail=inj.weights("abrupt",np.random.default_rng(0))
        self.assertLess(detail["observed_profile_fraction"],1.)
        self.assertEqual(n,len(des.d))
        self.assertGreater(detail["lost_to_unobserved_cells_fraction"],0)

    def test_out_of_window_delay_zero_signal(self):
        des=Design(event_window(synthetic(),BAN,"tight21"),BAN,"item_post"); inj=Injection(des,"tight21")
        for mode in ("equal_total","equal_intensity"):
            w,detail=inj.weights("delay28",np.random.default_rng(0),mode)
            self.assertEqual(w.sum(),0); self.assertEqual(detail["nominal_profile_fraction"],0)

    def test_equal_total_ramp_preserves_mass(self):
        des=Design(event_window(synthetic(),BAN,"tight21"),BAN,"item_post"); inj=Injection(des,"tight21")
        w,_=inj.weights("ramp21",np.random.default_rng(0),"equal_total"); self.assertAlmostEqual(w.sum(),1.)
        w,_=inj.weights("ramp21",np.random.default_rng(0),"equal_intensity"); self.assertLess(w.sum(),1.)

    def test_all_scenarios_finite(self):
        des=Design(event_window(synthetic(True),BAN,"tight21"),BAN,"twfe"); inj=Injection(des,"tight21")
        for scenario in SCENARIOS:
            w,detail=inj.weights(scenario,np.random.default_rng(1),"equal_intensity")
            self.assertTrue(np.isfinite(w).all()); self.assertTrue((w>=0).all())
            self.assertLessEqual(detail["observed_profile_fraction"],detail["nominal_profile_fraction"]+1e-12)

    def test_null_fit_orthogonal(self):
        for model in ("item_post","twfe"):
            des=Design(synthetic(True),BAN,model); fit=des.fit()
            self.assertAlmostEqual(des.beta(fit["null_fitted"]),0.,places=9)

    def test_block_draws_reproducible_and_nonnegative(self):
        des=Design(synthetic(),BAN,"twfe"); fit=des.fit()
        for b in ("neutral_model","observed_model"):
            y,c=bootstrap_log_outcome(des,fit,b,7,np.random.default_rng(44))
            y2,c2=bootstrap_log_outcome(des,fit,b,7,np.random.default_rng(44))
            np.testing.assert_array_equal(y,y2); self.assertTrue((y>=0).all()); self.assertEqual(c,c2)

    def test_seed_stream_separation(self):
        np.testing.assert_array_equal(label_seed(123,"A").random(10),label_seed(123,"A").random(10))
        self.assertFalse(np.array_equal(label_seed(123,"A").random(10),label_seed(123,"B").random(10)))

    def test_wilson_bounds(self):
        for k in (0,1,8,10):
            lo,hi=wilson(k,10); self.assertLessEqual(lo,k/10+1e-12); self.assertGreaterEqual(hi,k/10-1e-12)
            self.assertGreaterEqual(lo,0); self.assertLessEqual(hi,1)

    def test_floor_not_forced(self):
        g=np.array([0,10,20,30]); p=np.array([.03,.1,.2,.3])
        r=floor_brackets(g,p,np.maximum(p-.05,0),p+.05)
        self.assertEqual(r["status"],"not_reached_in_grid"); self.assertIsNone(r["crossing_upper_grid_pct"])

    def test_floor_bracket_no_interpolation(self):
        p=np.array([.05,.5,.79,.85]); g=np.array([0,10,20,40])
        r=floor_brackets(g,p,np.maximum(p-.03,0),p+.03)
        self.assertEqual(r["crossing_lower_grid_pct"],20); self.assertEqual(r["crossing_upper_grid_pct"],40)

    def test_panel_validation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"panel.csv"; d=synthetic(); d.to_csv(p,index=False)
            got,manifest=load_panel(p); self.assertEqual(len(got),len(d)); self.assertEqual(manifest["items"],20)
            pd.concat([d,d.iloc[:1]]).to_csv(p,index=False)
            with self.assertRaises(ValueError): load_panel(p)
            d.loc[0,"units"]=-1; d.to_csv(p,index=False)
            with self.assertRaises(ValueError): load_panel(p)

    def test_arm_change_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            d=synthetic(); d.loc[0,"arm"]="key"; p=Path(t)/"p.csv"; d.to_csv(p,index=False)
            with self.assertRaises(ValueError): load_panel(p)

    def test_container_exclusion_explicit(self):
        d=synthetic()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"exclude.csv"; pd.DataFrame({"item":["item_00"]}).to_csv(p,index=False)
            x,m=subset_panel(d,p); self.assertNotIn("item_00",set(x.item)); self.assertEqual(m["excluded_candidates"],1)
            pd.DataFrame({"item":["item_19"]}).to_csv(p,index=False)
            with self.assertRaises(ValueError): subset_panel(d,p)

    def test_no_mutation_of_input(self):
        d=synthetic(True); copy=d.copy(deep=True)
        des=Design(d,BAN,"twfe"); des.fit(); pd.testing.assert_frame_equal(d,copy)

    def test_unidentified_effect_rejected(self):
        d=synthetic(); d=d[d.arm=="candidate"]
        with self.assertRaises(ValueError): Design(d,BAN,"twfe")

if __name__=="__main__": unittest.main(verbosity=2)

from pathlib import Path
import numpy as np,pandas as pd,json
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_cluster,cov_cluster_2groups
from fe_engine import fit
ROOT=Path(__file__).resolve().parents[1]
rng=np.random.default_rng(44938);ni,nt=60,25
i=np.repeat(np.arange(ni),nt);t=np.tile(np.arange(nt),ni);keep=rng.random(len(i))>.2;i=i[keep];t=t[keep]
x=((i<30)&(t>=12)).astype(float);post=(t>=12).astype(float);y=rng.normal(size=len(i))+rng.normal(size=ni)[i]+rng.normal(size=nt)[t]+.17*x
checks=[]
for tw in [False,True]:
 X=x[:,None] if tw else np.c_[post,x]
 f=fit(y,X,i,t if tw else None)
 dummy=pd.get_dummies(i,drop_first=False,dtype=float).to_numpy()
 if tw:dummy=np.c_[dummy,pd.get_dummies(t,drop_first=True,dtype=float).to_numpy()]
 model=sm.OLS(y,np.c_[dummy,X]).fit()
 c1=cov_cluster(model,i)[-X.shape[1]:,-X.shape[1]:]
 db=float(np.max(np.abs(f['beta']-model.params[-X.shape[1]:])));dc=float(np.max(np.abs(f['cov_item']-c1)))
 assert db<1e-9 and dc<1e-9,(db,dc)
 rec={'two_way_fixed_effects':tw,'max_coefficient_error':db,'max_item_covariance_error':dc}
 if tw:
  c2=cov_cluster_2groups(model,i,t)[0][-1:,-1:];d2=float(np.max(np.abs(f['cov_two_way']-c2)))
  assert d2<1e-9,d2;rec['max_two_way_covariance_error']=d2
 # The precomputed linear coefficient weights must equal refitting for a nonlinear volume injection.
 y2=y+np.log1p(.3*rng.random(len(y)))
 f2=fit(y2,X,i,t if tw else None,covariance=False)
 dw=float(np.max(np.abs(f['weights']@y2-f2['beta'])));assert dw<1e-9;rec['injection_weight_identity_error']=dw
 checks.append(rec)
(ROOT/'audit/fe_engine_validation.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))

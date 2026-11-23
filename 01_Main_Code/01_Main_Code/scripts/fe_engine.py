"""Full-rank absorbed fixed effects; used only for labeled reconstruction/revision.
Coefficient equivalence and clustered covariance are validated against explicit dummy OLS.
"""
import numpy as np
from scipy import stats
def demean(a,g):
 a=np.asarray(a,dtype=float);one=a.ndim==1
 if one:a=a[:,None]
 sums=np.zeros((int(g.max())+1,a.shape[1]));np.add.at(sums,g,a)
 means=sums/np.bincount(g)[:,None]
 out=a-means[g]
 return out[:,0] if one else out
def absorb(a,item,date=None,tol=1e-11,maxiter=2000):
 out=np.asarray(a,dtype=float).copy()
 if date is None:return demean(out,item)
 for it in range(maxiter):
  prev=out;out=demean(demean(out,item),date)
  if np.max(np.abs(out-prev))<tol:return out
 raise RuntimeError('Alternating fixed-effect projection did not converge')
def cluster_meat(score,g):
 sums=np.zeros((int(g.max())+1,score.shape[1]));np.add.at(sums,g,score)
 return sums.T@sums
def fit(y,X,item,date=None,covariance=True):
 X=np.asarray(X,float)
 if X.ndim==1:X=X[:,None]
 Z=absorb(X,item,date);Y=absorb(y,item,date);bread=np.linalg.inv(Z.T@Z);b=bread@Z.T@Y
 u=Y-Z@b;n=len(y);gi=int(item.max())+1;gt=(int(date.max())+1) if date is not None else 0
 k=gi+X.shape[1]+(gt-1 if date is not None else 0)
 res={'beta':b,'n':n,'n_items':gi,'n_dates':gt,'rank':k,'weights':bread@Z.T,'residual':u,'z':Z}
 if covariance:
  score=Z*u[:,None];fac=(n-1)/(n-k)
  vi=bread@cluster_meat(score,item)@bread*fac*gi/(gi-1)
  res['cov_item']=vi
  if date is not None:
   vd=bread@cluster_meat(score,date)@bread*fac*gt/(gt-1)
   # Each retained row is one unique item-day; intersection cluster equals observation.
   vind=bread@(score.T@score)@bread*fac*n/(n-1)
   res['cov_two_way']=vi+vd-vind
 return res
def scalar_report(fit,col=-1):
 b=float(fit['beta'][col]);r={'coefficient':b,'percent_log_transform':100*np.expm1(b),'n':fit['n'],'items':fit['n_items'],'dates':fit['n_dates'],'rank':fit['rank']}
 for kind in ['item','two_way']:
  if 'cov_'+kind not in fit:continue
  variance=float(fit['cov_'+kind][col,col]);se=np.sqrt(variance) if variance>=0 else np.nan
  df=min(fit['n_items'],fit['n_dates'])-1 if kind=='two_way' else fit['n_items']-1
  r.update({f'se_{kind}':se,f'p_normal_{kind}':float(2*stats.norm.sf(abs(b/se))),f'p_t_{kind}':float(2*stats.t.sf(abs(b/se),df)),f'ci_low_{kind}':b-stats.t.ppf(.975,df)*se,f'ci_high_{kind}':b+stats.t.ppf(.975,df)*se,f'variance_{kind}':variance})
 return r

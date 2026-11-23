from pathlib import Path
import json,inspect,importlib.metadata,numpy as np,pandas as pd
from linearmodels.panel import PanelOLS
from revision_models import ROOT,EN,load_panel,group_subset,window,estimate
from fe_engine import fit
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups
rows=[];checks=[]
for group in ['all','exclude_cases','exclude_broad']:
 d=window(group_subset(load_panel('full'),group));d=d.set_index(['item_id','daynum']).sort_index();y=np.log1p(d.units);X=pd.DataFrame({'treat_post':d.treat*(d.index.get_level_values(1)>=EN)},index=d.index)
 mod=PanelOLS(y,X,entity_effects=True,time_effects=True,check_rank=True)
 ours=estimate(d.reset_index(),'TWFE')
 for label,kw in [('item',{'cov_type':'clustered','cluster_entity':True,'group_debias':True}),('item_and_date',{'cov_type':'clustered','cluster_entity':True,'cluster_time':True,'group_debias':True}),('DK_Bartlett3',{'cov_type':'kernel','kernel':'bartlett','bandwidth':3}),('DK_Bartlett7',{'cov_type':'kernel','kernel':'bartlett','bandwidth':7})]:
  res=mod.fit(low_memory=True,debiased=True,auto_df=False,count_effects=True,**kw)
  rows.append({'candidate_group':group,'covariance':label,'coefficient':res.params.iloc[0],'se':res.std_errors.iloc[0],'n':res.nobs,'df_model':res.df_model,'df_resid':res.df_resid,'linearmodels_version':importlib.metadata.version('linearmodels')})
  if label in ['item','item_and_date']:
   key='cov_item' if label=='item' else 'cov_two_way';db=abs(res.params.iloc[0]-ours['beta'][0]);dv=abs(res.cov.iloc[0,0]-ours[key][0,0]);assert db<1e-9 and dv<1e-9,(db,dv)
   checks.append({'group':group,'covariance':label,'beta_difference':db,'variance_difference':dv})
rng=np.random.default_rng(14938)
for balanced in [True,False]:
 i=np.repeat(np.arange(30),20);t=np.tile(np.arange(20),30);keep=np.ones(len(i),bool) if balanced else rng.random(len(i))>.2;i=i[keep];t=t[keep];x=((i<15)&(t>=10)).astype(float);y=rng.normal(size=len(i))+.2*x+rng.normal(size=30)[i]+rng.normal(size=20)[t]
 idx=pd.MultiIndex.from_arrays([i,t]);lm=PanelOLS(pd.Series(y,index=idx),pd.DataFrame({'x':x},index=idx),entity_effects=True,time_effects=True).fit(low_memory=True,cov_type='clustered',cluster_entity=True,cluster_time=True,auto_df=False,count_effects=True,debiased=True,group_debias=True)
 design=np.c_[pd.get_dummies(i,drop_first=False,dtype=float),pd.get_dummies(t,drop_first=True,dtype=float),x];ols=sm.OLS(y,design).fit();cov=cov_cluster_2groups(ols,i,t)[0][-1,-1]
 f=fit(y,x,i,t);db=max(abs(lm.params.iloc[0]-ols.params[-1]),abs(f['beta'][0]-ols.params[-1]));dv=max(abs(lm.cov.iloc[0,0]-cov),abs(f['cov_two_way'][0,0]-cov));assert db<1e-9 and dv<1e-9
 checks.append({'balanced':balanced,'small_sample_beta_max_error':db,'small_sample_covariance_max_error':dv})
pd.DataFrame(rows).to_csv(ROOT/'corrected_analysis/linearmodels_and_temporal_dependence.csv',index=False)
(ROOT/'audit/linearmodels_crosscheck.json').write_text(json.dumps({'checks':checks,'fit_signature':str(inspect.signature(PanelOLS.fit)),'note':'Same-agent computational cross-check, not independent human replication. DK with42dates is a sensitivity, not a small-sample guarantee.'},indent=2))
print(pd.DataFrame(rows).to_string(index=False));print('PANELOLS_CROSSCHECK_PASSED')

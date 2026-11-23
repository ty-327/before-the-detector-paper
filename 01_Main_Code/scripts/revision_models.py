from pathlib import Path
import json, numpy as np,pandas as pd
from scipy import stats
from fe_engine import fit,scalar_report
ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'revision/REVISION_SETTINGS.json').read_text())
E=pd.Timestamp('2019-10-28',tz='UTC');EN=(E-pd.Timestamp('1970-01-01',tz='UTC')).days
def load_panel(which='full'):
 p=pd.read_parquet(ROOT/('historical/full_zip_panel_vectorized.parquet' if which=='full' else 'historical/recovered_panel.parquet'))
 if which=='full':p['arm']=p.whole_word_arm
 else:
  m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv');p['item_id']=p.item.astype(str).map(dict(zip(m.item,m.item_id)))
  p['daynum']=((p.day-pd.Timestamp('1970-01-01',tz='UTC')).dt.days).astype(int)
 p=p[p.arm.isin(['substitute','control'])].copy();p['treat']=(p.arm=='substitute').astype(float)
 return p
def group_subset(p,group):
 if group=='all':return p
 c=pd.read_csv(ROOT/'revision/container_definitions.csv');col='key_dependent_case' if group=='exclude_cases' else 'all_named_containers'
 return p[~p.item_id.isin(c.loc[c[col],'item_id'])]
def window(p,event=EN,low=-21,high=20):return p[p.daynum.between(event+low,event+high)].copy()
def arrays(d,event=EN):
 i=pd.factorize(d.item_id,sort=True)[0];t=pd.factorize(d.daynum,sort=True)[0];post=(d.daynum>=event).to_numpy(float);tr=d.treat.to_numpy(float);y=np.log1p(d.units.to_numpy(float))
 return y,np.c_[post,post*tr],i,t
def estimate(d,model,event=EN,covariance=True):
 y,X,i,t=arrays(d,event)
 return fit(y,X[:,1:] if model=='TWFE' else X,i,t if model=='TWFE' else None,covariance)
def shape_profile(t,shape):
 t=np.asarray(t);pos=np.maximum(t+1,0)
 if shape=='step':return (t>=0).astype(float)
 if shape.startswith('ramp'):return np.clip(pos/int(shape[4:]),0,1)
 if shape.startswith('delay'):return (t>=int(shape[5:])).astype(float)
 if shape=='distributed_uniform_onset0to20':return np.clip(pos/21,0,1)
 if shape=='heterogeneous_exponential_onset0to7_tau_lognormal_median7_sigma0.6':
  nodes,weights=np.polynomial.hermite.hermgauss(40);tau=7*np.exp(.6*np.sqrt(2)*nodes);ans=np.zeros(len(t))
  for delay in range(8):
   a=np.maximum(t-delay+1,0);ans+=(1-np.exp(-a[:,None]/tau))@weights/np.sqrt(np.pi)/8
  return ans
 raise ValueError(shape)
def main():
 results=[];profiles=[];eventrows=[];tests=[]
 for cohort in ['recovered','full']:
  p=load_panel(cohort)
  for group in ['all','exclude_cases','exclude_broad']:
   q=group_subset(p,group)
   specs=[('corrected_42days',EN,-21,20),('historical_43days',EN,-21,21),('wide_181days_confounded',EN,-90,90),('omit_event_day',EN,-21,20),('shift_event_next_UTC_day',EN+1,-21,20),('zero_fill_hypothesis',EN,-21,20),('complete_case_only',EN,-21,20)]
   for label,event,low,high in specs:
    d=window(q,event,low,high)
    if label=='omit_event_day':d=d[d.daynum!=event]
    if label=='complete_case_only':
     counts=d.groupby('item_id').daynum.nunique();d=d[d.item_id.isin(counts[counts==high-low+1].index)]
    if label=='zero_fill_hypothesis':
     meta=q[['item_id','treat']].drop_duplicates();idx=pd.MultiIndex.from_product([meta.item_id,np.arange(event+low,event+high+1)],names=['item_id','daynum'])
     d=d.set_index(['item_id','daynum'])[['units']].reindex(idx).fillna(0).reset_index().merge(meta,on='item_id',validate='many_to_one')
    for model in ['item_FE','TWFE']:
     f=estimate(d,model,event);r={'cohort':cohort,'candidate_group':group,'specification':label,'model':model,'event_daynum':event,'low':low,'high':high,**scalar_report(f)}
     r['candidate_items']=d.loc[d.treat==1,'item_id'].nunique();r['control_items']=d.loc[d.treat==0,'item_id'].nunique();results.append(r)
   print('Completed robustness',cohort,group,flush=True)
   if cohort!='full':continue
   d=window(q);y,X,i,t=arrays(d);rel=(d.daynum-EN).to_numpy();tr=d.treat.to_numpy()
   for shape in CFG['empirical_response_shapes']:
    f=fit(y,tr*shape_profile(rel,shape),i,t);profiles.append({'candidate_group':group,'shape':shape,**scalar_report(f)})
   offsets=[k for k in range(-21,21) if k!=-1];Z=np.column_stack([tr*(rel==k) for k in offsets]);f=fit(y,Z,i,t)
   for j,k in enumerate(offsets):eventrows.append({'candidate_group':group,'offset':k,**scalar_report(f,j)})
   pre=np.array([j for j,k in enumerate(offsets) if k<-1]);b=f['beta'][pre];cov=f['cov_item'][np.ix_(pre,pre)];w=float(b@np.linalg.pinv(cov)@b);rank=int(np.linalg.matrix_rank(cov))
   tests.append({'candidate_group':group,'wald_chi2':w,'df':rank,'p_chi2':float(stats.chi2.sf(w,rank)),'reference_day':-1,'lead_range':'-21 through-2','inference':'joint item-cluster covariance; no multiple-testing adjustment'})
 pd.DataFrame(results).to_csv(ROOT/'tables/revision_robustness.csv',index=False)
 pd.DataFrame(profiles).to_csv(ROOT/'tables/empirical_response_shapes.csv',index=False)
 pd.DataFrame(eventrows).to_csv(ROOT/'tables/twfe_event_study.csv',index=False)
 pd.DataFrame(tests).to_csv(ROOT/'tables/twfe_pretrend_tests.csv',index=False)
 print(pd.DataFrame(results).query("specification=='corrected_42days'")[['cohort','candidate_group','model','coefficient','se_item','se_two_way']].to_string(index=False),flush=True)
 print('REVISION_MODELS_COMPLETE',flush=True)
if __name__=='__main__':main()

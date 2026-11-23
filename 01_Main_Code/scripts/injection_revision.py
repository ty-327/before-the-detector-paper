"""New, prespecified revision simulation. This is NOT recovered submitted injection code.
Linear FE weights exactly re-estimate each synthetic outcome; independent validation is retained.
"""
from pathlib import Path
import json,sys,copy, numpy as np,pandas as pd
from scipy.stats import norm
from revision_models import ROOT,CFG,EN,load_panel,group_subset,window,estimate
V2='--v2' in sys.argv;EQUAL='--equal-cumulative' in sys.argv
OUT=ROOT/('revision_extensions/v2_equal_cumulative' if EQUAL else 'revision_extensions/v2') if V2 else ROOT
IC=(json.loads((ROOT/'revision_extensions/v2/REVISION_SETTINGS_V2.json').read_text()) if V2 else CFG)['injection']
GROUPS=['all','exclude_cases','exclude_broad'];MODELS=['item_FE','TWFE']
if EQUAL:
 IC=copy.deepcopy(IC);IC['shapes']=IC['equal_cumulative_sensitivity']['shapes'];GROUPS=['all','exclude_cases'];MODELS=['TWFE']
GRID=np.array(IC['grid_fraction']);R=IC['repetitions'];B=IC['bootstrap_repetitions']
def wilson(k,n):
 z=norm.ppf(.975);p=k/n;den=1+z*z/n;mid=(p+z*z/(2*n))/den;half=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return mid-half,mid+half
def first_floor(power):
 hits=np.flatnonzero(power>=IC['target_power']);return float(GRID[hits[0]]) if len(hits) else np.inf
def interval_higher(values):return np.quantile(values,[.025,.975],method='higher')
def allocations(d,seed):
 rng=np.random.default_rng(seed);sub=d[d.treat==1];ids=np.sort(sub.item_id.unique());lookup={v:j for j,v in enumerate(ids)}
 pre=sub[sub.daynum<EN].groupby('item_id').units.sum().reindex(ids,fill_value=0).to_numpy(float)/21
 postmask=((d.treat==1)&(d.daynum>=EN)).to_numpy();post=d.loc[postmask];idx=post.item_id.map(lookup).to_numpy(int);t=(post.daynum-EN).to_numpy(int)
 allocations={}
 for shape in IC['shapes']:
  if shape=='step':f=np.ones((1,len(post)))
  elif shape.startswith('ramp'):f=np.clip((t+1)/int(shape[4:]),0,1)[None,:]
  elif shape.startswith('delay'):f=(t>=int(shape[5:])).astype(float)[None,:]
  elif shape=='distributed':
   onset=rng.integers(0,21,size=(R,len(ids)));f=(t[None,:]>=onset[:,idx]).astype(float)
  elif shape=='heterogeneous':
   onset=rng.integers(0,8,size=(R,len(ids)));tau=7*np.exp(.6*rng.normal(size=(R,len(ids))));f=1-np.exp(-np.maximum(t[None,:]-onset[:,idx]+1,0)/tau[:,idx])
  elif shape=='concentrated10pct':
   active=np.zeros((R,len(ids)))
   for r in range(R):active[r,rng.choice(len(ids),int(np.ceil(.1*len(ids))),replace=False)]=1
   scale=pre.sum()/(active@pre);f=active[:,idx]*scale[:,None]
  else:raise ValueError(shape)
  W=f*pre[idx][None,:]
  if EQUAL:
   denom=W.sum(axis=1)
   if np.any(denom<=0):raise ValueError('Cannot normalize a zero in-window signal')
   W=W*(pre.sum()*21/denom)[:,None]
  allocations[shape]=W
 return postmask,allocations,float(pre.sum()*21),ids
def main():
 (OUT/'tables').mkdir(parents=True,exist_ok=True)
 calibration=pd.read_csv(ROOT/'tables/date_calibration_full_calendar.csv');p=load_panel('full');curve_rows=[];floor_rows=[];threshold_rows=[]
 for gi,group in enumerate(GROUPS):
  d=window(group_subset(p,group));postmask,alloc,budget,ids=allocations(d,IC['seed']+gi*100)
  for mi,model in enumerate(MODELS):
   f=estimate(d,model,covariance=False);beta=float(f['beta'][-1]);weight=f['weights'][-1,postmask]
   full=calibration[(calibration.candidate_group==group)&(calibration.model==model)].sort_values('daynum')
   frozen=full[full.in_frozen150];b=frozen.coefficient.to_numpy();allb=full.coefficient.to_numpy();clean=frozen[~frozen.overlaps_trade_hold].coefficient.to_numpy()
   threshold=np.quantile(b,.95)-b.mean();rng=np.random.default_rng(IC['seed']+10000+gi*100+mi)
   noise_indices=rng.integers(0,len(b),size=R);noise=b[noise_indices]-b.mean()
   bootrng=np.random.default_rng(IC['bootstrap_seed']+gi*100+mi)
   # Use common bootstrap draws across shapes/backgrounds for paired comparisons.
   iid_indices=bootrng.integers(0,len(b),size=(B,len(b)));iid_values=b[iid_indices]
   block_indices=[];length=IC['block_days'];n=len(allb)
   for _ in range(B):
    starts=bootrng.integers(0,n,size=int(np.ceil(n/length)));block_indices.append(((starts[:,None]+np.arange(length))%n).ravel()[:n])
   block_indices=np.array(block_indices);block_values=allb[block_indices]
   boot_run_indices=bootrng.integers(0,R,size=(B,R))
   boot_noise_iid=bootrng.integers(0,len(b),size=(B,R));boot_noise_block=bootrng.integers(0,n,size=(B,R))
   q_iid=np.quantile(iid_values,.95,axis=1)-iid_values.mean(axis=1);q_block=np.quantile(block_values,.95,axis=1)-block_values.mean(axis=1)
   thresholds={'frozen150':threshold,'exclude_trade_hold':np.quantile(clean,.95)-clean.mean(),'full_calendar':np.quantile(allb,.95)-allb.mean()}
   threshold_rows.append({'candidate_group':group,'model':model,**{f'q95_{k}':v for k,v in thresholds.items()},'iid_q95_low':interval_higher(q_iid)[0],'iid_q95_high':interval_higher(q_iid)[1],'block_q95_low':interval_higher(q_block)[0],'block_q95_high':interval_higher(q_block)[1]})
   ndir=OUT/'revision/simulation_draws';ndir.mkdir(exist_ok=True,parents=True)
   np.savez_compressed(ndir/f'{group}_{model}_randomness.npz',noise_indices=noise_indices,iid_indices=iid_indices,block_indices=block_indices,bootstrap_run_indices=boot_run_indices,bootstrap_noise_iid=boot_noise_iid,bootstrap_noise_block=boot_noise_block)
   for background in ['neutral','observed']:
    q=d.loc[postmask,'units'].to_numpy(float)
    if background=='neutral':q=np.expm1(np.log1p(q)-beta);base=0.
    else:base=beta
    if np.any(q<0):raise ValueError('Neutralized volume became negative; no silent clipping permitted')
    for shape,W in alloc.items():
     signal=np.empty((R,len(GRID)))
     for j,delta in enumerate(GRID):
      # log1p(q+delta*W)-log1p(q), expressed stably; candidate post rows are the only changed outcomes.
      s=np.log1p(delta*W/(1+q)[None,:])@weight
      signal[:,j]=s if len(s)>1 else s[0]
     coeff=base+signal+noise[:,None];success=coeff>threshold;power=success.mean(axis=0)
     volume_fraction=W.sum(axis=1)/budget
     for j,delta in enumerate(GRID):
      low,high=wilson(int(success[:,j].sum()),R)
      curve_rows.append({'candidate_group':group,'model':model,'background':background,'shape':shape,'terminal_fraction':delta,'mean_added_flow_fraction':delta*volume_fraction.mean(),'added_flow_fraction_p025':delta*np.quantile(volume_fraction,.025),'added_flow_fraction_p975':delta*np.quantile(volume_fraction,.975),'detections':int(success[:,j].sum()),'repetitions':R,'power':power[j],'wilson_low':low,'wilson_high':high,'threshold':threshold})
     floors_iid=[];floors_block=[]
     for j in range(B):
      sig=signal[boot_run_indices[j]]
      ei=iid_values[j,boot_noise_iid[j]]-iid_values[j].mean();eb=block_values[j,boot_noise_block[j]]-block_values[j].mean()
      floors_iid.append(first_floor((base+sig+ei[:,None]>q_iid[j]).mean(axis=0)))
      floors_block.append(first_floor((base+sig+eb[:,None]>q_block[j]).mean(axis=0)))
     floor=first_floor(power);floornum=np.flatnonzero(GRID==floor);lower=GRID[floornum[0]-1] if len(floornum) and floornum[0]>0 else (0 if floor==0 else GRID[-1])
     ci=interval_higher(floors_iid);cb=interval_higher(floors_block)
     # Calibration sensitivities rerun the disturbance draw against each declared distribution.
     sense={}
     for tag,values in [('exclude_trade_hold',clean),('full_calendar',allb)]:
      srng=np.random.default_rng(IC['seed']+222+gi*100+mi);e=srng.choice(values,R)-values.mean()
      sense[f'floor_{tag}']=first_floor((base+signal+e[:,None]>thresholds[tag]).mean(axis=0))
     if V2:
      train=full[full.date.between('2017-03-01','2018-12-10')].coefficient.to_numpy();test=full[full.date.between('2019-02-01','2019-08-31')].coefficient.to_numpy()
      hrng=np.random.default_rng(IC['seed']+333+gi*100+mi);he=hrng.choice(test,R)-test.mean();sense['floor_disjoint_calendar_holdout']=first_floor((base+signal+he[:,None]>(np.quantile(train,.95)-train.mean())).mean(axis=0))
     robust_floor=first_floor(np.array([wilson(int(k),R)[0] for k in success.sum(axis=0)]))
     floor_rows.append({'candidate_group':group,'model':model,'background':background,'shape':shape,'floor_fraction':floor,'grid_lower_bracket':lower,'iid_bootstrap_low':ci[0],'iid_bootstrap_high':ci[1],'block_bootstrap_low':cb[0],'block_bootstrap_high':cb[1],'bootstrap_iid_fraction_above_grid':np.mean(np.isinf(floors_iid)),'bootstrap_block_fraction_above_grid':np.mean(np.isinf(floors_block)),'floor_with_wilson_lower_bound80':robust_floor,'mean_added_flow_fraction_at_floor':floor*volume_fraction.mean(),**sense})
     np.savez_compressed(ndir/f'{group}_{model}_{background}_{shape}.npz',grid=GRID,signal=signal,coefficients=coeff,success=success,volume_fraction=volume_fraction,bootstrap_floors_iid=floors_iid,bootstrap_floors_block=floors_block)
     print('Injection',group,model,background,shape,'floor',floor,'iid95',ci,'block95',cb,flush=True)
    frame=pd.DataFrame(curve_rows);frame['monte_carlo_se']=np.sqrt(frame.power*(1-frame.power)/R);frame['signal_scale']='equal_cumulative' if EQUAL else 'eventual_daily_intensity';frame.to_csv(OUT/'tables/injection_power_curves.csv',index=False);pd.DataFrame(floor_rows).to_csv(OUT/'tables/detection_floors.csv',index=False)
   pd.DataFrame(threshold_rows).to_csv(OUT/'tables/calibration_threshold_uncertainty.csv',index=False)
 print('INJECTION_REVISION_COMPLETE',flush=True)
if __name__=='__main__':main()

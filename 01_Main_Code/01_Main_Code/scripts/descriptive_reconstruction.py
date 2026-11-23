from pathlib import Path
import json,numpy as np,pandas as pd
from fe_engine import scalar_report
from revision_models import ROOT,EN,estimate
p=pd.read_parquet(ROOT/'historical/full_zip_panel_vectorized.parquet')
oldnames=set(pd.read_parquet(ROOT/'historical/recovered_panel.parquet',columns=['item']).item.astype(str))
rows=[];h1=[];volume=[];contrast=[]
containers=pd.read_csv(ROOT/'revision/container_definitions.csv');cases=set(containers.loc[containers.key_dependent_case,'item_id'])
for scope in ['historical_recovered_cohort','full_zip']:
 q=p[p.item.astype(str).isin(oldnames)].copy() if scope.startswith('historical') else p.copy()
 for keyversion in ['substring_30keys','whole_word_27keys']:
  key=q[(q.arm=='key') if keyversion.startswith('substring') else (q.whole_word_arm=='key')]
  sub=q[q.arm=='substitute']
  prekey=key[key.daynum<EN].copy();presub=sub[sub.daynum<EN].copy()
  km=prekey.groupby(prekey.day.dt.strftime('%Y-%m')).units.sum();sm=presub.groupby(presub.day.dt.strftime('%Y-%m')).units.sum();rat=(km/sm).dropna()
  base=rat[rat.index<'2018-10'].mean();late=rat[rat.index>='2018-10'].mean()
  h1.append({'scope':scope,'keys':keyversion,'baseline_mean_monthly_ratio':base,'final_period_mean_monthly_ratio':late,'ratio_change_percent':100*(late/base-1),'final_period_months':int((rat.index>='2018-10').sum()),'last_month_partial':True,'pre21_key_to_candidate_volume':key[key.daynum.between(EN-21,EN-1)].units.sum()/sub[sub.daynum.between(EN-21,EN-1)].units.sum()})
  for year in range(2017,2025):
   kd=key[key.day.dt.year==year];sd=sub[sub.day.dt.year==year]
   for recipe in ['equal_item_daily_mean_then_equal_days','pooled_unit_weighted_all_rows']:
    if recipe.startswith('equal'):
     k=kd.groupby('day').vwap.mean().mean();s=sd.groupby('day').vwap.mean().mean()
    else:
     k=(kd.vwap*kd.units).sum()/kd.units.sum();s=(sd.vwap*sd.units).sum()/sd.units.sum()
    rows.append({'scope':scope,'keys':keyversion,'year':year,'recipe':recipe,'key_price':k,'candidate_index':s,'ratio':k/s})
 for high in [20,21]:
  d=q[q.daynum.between(EN-21,EN+high)&(q.arm!='key')].copy();d['treat']=(d.arm=='substitute').astype(float)
  for label,mask in [('all_candidates',d.arm=='substitute'),('cases',d.item_id.isin(cases)),('other_candidates',(d.arm=='substitute')&~d.item_id.isin(cases)),('controls',d.arm=='control')]:
   v=d[mask];before=v[v.daynum<EN].units.sum()/21;after=v[v.daynum>=EN].units.sum()/(high+1)
   volume.append({'scope':scope,'post_last_offset':high,'group':label,'pre_daily_units':before,'post_daily_units':after,'aggregate_change_percent':100*(after/before-1)})
   if label!='controls':
    selected=d[mask|(d.arm=='control')].copy();f=estimate(selected,'item_FE');contrast.append({'scope':scope,'post_last_offset':high,'candidate_group':label,**scalar_report(f)})
pd.DataFrame(h1).to_csv(ROOT/'tables/h1_reconstruction.csv',index=False)
pd.DataFrame(rows).to_csv(ROOT/'tables/h3_index_construction_sensitivity.csv',index=False)
pd.DataFrame(volume).to_csv(ROOT/'tables/aggregate_volume_changes.csv',index=False)
pd.DataFrame(contrast).to_csv(ROOT/'tables/container_historical_contrasts.csv',index=False)
print(pd.DataFrame(h1).to_string(index=False));print(pd.DataFrame(rows).query("scope=='historical_recovered_cohort' and keys=='whole_word_27keys' and recipe=='equal_item_daily_mean_then_equal_days'").to_string(index=False))

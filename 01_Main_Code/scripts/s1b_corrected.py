"""Revision-stage S1b sensitivities, explicitly separate from literal historical outputs."""
from pathlib import Path
import json,re,numpy as np,pandas as pd
from revision_models import ROOT
M=pd.read_csv(ROOT/'corrected_analysis/item_classification_audit.csv')
M['canonical_name']=M.conversion_table_decoded.fillna(M.simple_percent_decode)
WEAR=('Factory New','Minimal Wear','Field-Tested','Well-Worn','Battle-Scarred')
def cat(n):
 if re.search(r'\bKey\b',n):return 'excluded','KEY'
 if any(w in n for w in WEAR):return 'nonfungible','NF'
 for term in ['Sticker','Graffiti','Pin','Patch']:
  if n.startswith(term+' |') or n.startswith('Sealed '+term+' |'):return 'fungible',term
 for term in ['Case','Capsule','Package','Sticker','Graffiti','Pin','Patch']:
  if re.search(r'\b'+term+r'\b',n):return 'fungible',term
 return 'excluded','OTHER'
M[['s1b_arm','peer']]=pd.DataFrame(M.canonical_name.map(cat).tolist(),index=M.index)
M=M[(M.s1b_arm!='excluded')&(M.usable_raw_rows>=30)&(M.observed_days>=30)].copy().set_index('item_id')
M['s1b_container']=M.peer.isin(['Case','Capsule','Package']);cut=M.all_med_units.quantile([.2,.4,.6,.8]).to_numpy();M['quintile']=np.searchsorted(cut,M.all_med_units,side='right')+1
M.to_csv(ROOT/'corrected_analysis/s1b_item_eligibility.csv')
def spike_fields(days,prices,units,j):
 targets=days[j]+np.arange(1,4);where=np.searchsorted(days,targets);present=(where<len(days));present[present]=days[where[present]]==targets[present]
 pre=prices[j-1];reverted=bool(np.any(np.abs(prices[where[present]]-pre)/pre<=.25))
 known=reverted or bool(present.all())
 return {'reverted_historical':reverted,'followup_observable':known,'followup_all_three_days':bool(present.all()),'pre_vwap':pre,'spike_vwap':prices[j],'units_at_spike':units[j]}
def main():
 records=[];retparts=[];opps=[]
 for part in sorted((ROOT/'audit/daily_cache').glob('*.parquet')):
  d=pd.read_parquet(part);d=d[d.item_id.isin(M.index)]
  for iid,v in d.groupby('item_id',sort=False):
   row=M.loc[iid];days=v.daynum.to_numpy();prices=v.vwap.to_numpy();units=v.units.to_numpy();ret=np.r_[np.nan,prices[1:]/prices[:-1]-1];consecutive=np.r_[False,np.diff(days)==1]
   opps.append({'item_id':iid,'observed_days':len(v),'observed_return_opportunities':len(v)-1,'consecutive_return_opportunities':int(consecutive.sum())})
   if consecutive.any():retparts.append(pd.DataFrame({'peer':row.peer,'daynum':days[consecutive],'ret':ret[consecutive]}))
   for j in np.flatnonzero(ret>1):records.append({'item_id':iid,'daynum':days[j],'ret':ret[j],'gap_days':int(days[j]-days[j-1]),'consecutive':bool(consecutive[j]),**spike_fields(days,prices,units,j)})
  print('S1b corrected cache',part.name,flush=True)
 S=pd.DataFrame(records).merge(M.reset_index()[['item_id','canonical_name','s1b_arm','peer','mean_raw_price','all_med_units','quintile','s1b_container']],on='item_id',validate='many_to_one')
 O=pd.DataFrame(opps).merge(M.reset_index()[['item_id','s1b_arm','mean_raw_price','quintile','s1b_container']],on='item_id',validate='one_to_one');O.to_csv(ROOT/'corrected_analysis/s1b_return_opportunities.csv',index=False)
 returns=pd.concat(retparts,ignore_index=True);del retparts
 peer={}
 for key,v in returns.groupby(['peer','daynum'],sort=False).ret:
  a=np.sort(v.to_numpy());n=len(a);k=n//2;lo=a[max(k-1,0)];mid=a[k];hi=a[min(k+1,n-1)];med=(lo+mid)/2 if n%2==0 else mid;peer[key]=(n,lo,mid,hi,med)
 del returns
 inc=[];loo=[]
 for r in S.itertuples():
  if not r.consecutive:inc.append(np.nan);loo.append(np.nan);continue
  n,lo,mid,hi,med=peer[(r.peer,r.daynum)];inc.append(med)
  if n<=1:loo.append(np.nan)
  elif n%2==0:loo.append(mid if r.ret<=lo else lo)
  else:loo.append((mid+hi)/2 if r.ret<mid else ((lo+mid)/2 if r.ret>mid else (lo+hi)/2))
 S['peer_including_focal']=inc;S['peer_excluding_focal']=loo;S['peer_idio_inclusive']=np.where(S.peer_including_focal.notna(),abs(S.peer_including_focal)<.1,np.nan);S['peer_idio_leave_one_out']=np.where(S.peer_excluding_focal.notna(),abs(S.peer_excluding_focal)<.1,np.nan)
 S.to_csv(ROOT/'corrected_analysis/s1b_corrected_spikes.csv',index=False)
 rows=[];quints=[]
 for variant in ['whole_word_observed_returns','consecutive_calendar_returns','consecutive_exclude_containers']:
  ss=S.copy();oo=O.copy();den='observed_days'
  if variant!='whole_word_observed_returns':ss=ss[ss.consecutive];den='consecutive_return_opportunities'
  if variant=='consecutive_exclude_containers':ss=ss[~ss.s1b_container];oo=oo[~oo.s1b_container]
  for filt in ['mean_price_gt10','all_prices']:
   s=ss[ss.mean_raw_price>10] if filt=='mean_price_gt10' else ss;o=oo[oo.mean_raw_price>10] if filt=='mean_price_gt10' else oo
   for arm in ['fungible','nonfungible']:
    a=s[s.s1b_arm==arm];b=o[o.s1b_arm==arm];nd=int(b[den].sum());known=a[a.followup_observable]
    rows.append({'variant':variant,'price_filter':filt,'arm':arm,'items':len(b),'denominator_kind':den,'denominator':nd,'spikes':len(a),'rate_per1000':1000*len(a)/nd,'spikes_after_gap_gt1':int((a.gap_days>1).sum()),'reversion_historical_percent':100*a.reverted_historical.mean(),'observable_followup_spikes':len(known),'censored_no_observed_reversion':len(a)-len(known),'reversion_observable_followup_percent':100*known.reverted_historical.mean(),'peer_idio_inclusive_percent':100*a.peer_idio_inclusive.mean(),'peer_idio_leave_one_out_percent':100*a.peer_idio_leave_one_out.mean(),'median_spike_units':a.units_at_spike.median()})
    for quint in range(1,6):
     aq=a[a.quintile==quint];bq=b[b.quintile==quint];n=int(bq[den].sum());quints.append({'variant':variant,'price_filter':filt,'arm':arm,'quintile':quint,'spikes':len(aq),'denominator':n,'rate_per1000':1000*len(aq)/n if n else np.nan})
 pd.DataFrame(rows).to_csv(ROOT/'corrected_analysis/s1b_sensitivity_summary.csv',index=False);pd.DataFrame(quints).to_csv(ROOT/'corrected_analysis/s1b_quintile_sensitivities.csv',index=False)
 print(pd.DataFrame(rows).query("price_filter=='mean_price_gt10'").to_string(index=False))
 print('S1B_CORRECTED_COMPLETE')
if __name__=='__main__':main()

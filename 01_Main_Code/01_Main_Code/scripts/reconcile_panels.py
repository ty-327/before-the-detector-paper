from pathlib import Path
import json, numpy as np,pandas as pd
from fe_engine import fit,scalar_report
ROOT=Path(__file__).resolve().parents[1]
m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv')
selected=m[m.historical_arm!='excluded'];chunks=[]
for p in sorted((ROOT/'audit/daily_cache').glob('part_*.parquet')):
 d=pd.read_parquet(p);chunks.append(d[d.item_id.isin(selected.item_id)])
p=pd.concat(chunks,ignore_index=True);p=p.merge(m[['item_id','item','historical_arm','whole_word_arm','historical_class','container_case','container_broad']],on='item_id',validate='many_to_one')
p['day']=pd.to_datetime(p.daynum,unit='D',utc=True);p=p.rename(columns={'historical_arm':'arm','historical_class':'group'})
for c in ['item','arm','whole_word_arm','group']:p[c]=p[c].astype('category')
p.to_parquet(ROOT/'historical/full_zip_panel_vectorized.parquet',index=False)
old=pd.read_parquet(ROOT/'historical/recovered_panel.parquet');old['item_id']=old.item.astype(str).map(dict(zip(m.item,m.item_id)));old['daynum']=((old.day-pd.Timestamp('1970-01-01',tz='UTC')).dt.days).astype(int)
joined=old.merge(p[['item_id','daynum','units','vwap']],on=['item_id','daynum'],suffixes=('_old','_zip'),how='outer',indicator=True)
both=joined[joined._merge=='both']
out={'recovered_rows':len(old),'raw_rebuilt_selected_rows':len(p),'common_rows':len(both),'recovered_rows_missing_from_rebuild':int((joined._merge=='left_only').sum()),'new_rows_not_in_recovered':int((joined._merge=='right_only').sum()),'common_unit_mismatches':int((both.units_old!=both.units_zip).sum()),'common_max_vwap_absolute_difference':float(np.max(np.abs(both.vwap_old-both.vwap_zip))),'common_vwap_mismatches_tolerance_1e_10':int((np.abs(both.vwap_old-both.vwap_zip)>1e-10).sum())}
added=selected[~selected.item.isin(old.item.astype(str))].copy();added.to_csv(ROOT/'tables/additional_items_in_full_zip.csv',index=False)
out['additional_selected_items']=added.groupby('historical_arm').size().to_dict();out['all_75_absent_filenames_raw_rows']=int(m[m.file.isin(json.loads((ROOT/'audit/raw_audit.json').read_text())['present_new_missing_old'])].raw_rows.sum())
out['full_raw_rows']=int(m.raw_rows.sum());out['old_folder_file_set_raw_rows']=out['full_raw_rows']-out['all_75_absent_filenames_raw_rows']
results=[]
for cohort,data in [('recovered_panel',old),('full_zip_historical_rules',p)]:
 for event,low,high in [('2019-10-28',-21,21),('2019-10-28',-90,90),('2017-06-15',-21,21),('2018-03-20',-21,21),('2018-09-10',-21,21)]:
  e=pd.Timestamp(event,tz='UTC');d=data[(data.arm!='key') & data.day.between(e+pd.Timedelta(days=low),e+pd.Timedelta(days=high))].copy()
  ids=pd.factorize(d.item,sort=True)[0];post=(d.day>=e).to_numpy(float);tr=(d.arm=='substitute').to_numpy(float)
  f=fit(np.log1p(d.units.to_numpy()),np.c_[post,post*tr],ids)
  r={'cohort':cohort,'event':event,'low':low,'high':high,'estimator':'full-rank reconstruction of historical item-FE estimand',**scalar_report(f)};results.append(r)
pd.DataFrame(results).to_csv(ROOT/'tables/baseline_full_rank_reconstruction.csv',index=False)
(ROOT/'audit/panel_reconciliation.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2));print(pd.DataFrame(results)[['cohort','event','low','high','coefficient','se_item']].to_string(index=False),flush=True)

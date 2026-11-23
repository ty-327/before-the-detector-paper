from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np,pandas as pd,json
from revision_models import ROOT,EN,load_panel,estimate,window
def process(arg):
 item_id,file=arg;d=pd.read_csv(ROOT/'inputs/download_snapshot/items'/file)
 textday=pd.to_datetime(d.date.str.slice(0,11),format='%b %d %Y',utc=True)
 unixday=pd.to_datetime(d['unix timestamp'],unit='s',utc=True).dt.floor('D')
 lo=pd.Timestamp('2017-02-08',tz='UTC');hi=pd.Timestamp('2020-01-27',tz='UTC')
 inrange=textday.between(lo,hi)|unixday.between(lo,hi)
 totaldiff=int((textday[inrange]!=unixday[inrange]).sum())
 d=d.loc[inrange].assign(day=textday[inrange]);d['pq']=d.price*d.quantity
 daily=d.groupby('day').agg(units=('quantity','sum'),value=('pq','sum')).reset_index();daily['vwap']=daily.value/daily.units;daily=daily.drop(columns='value');daily['item_id']=item_id
 return totaldiff,daily
if __name__=='__main__':
 m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv');m=m[m.whole_word_arm.isin(['substitute','control'])];chunks=[];count=0
 with ProcessPoolExecutor(max_workers=6) as pool:
  for i,(diff,d) in enumerate(pool.map(process,zip(m.item_id,m.file),chunksize=20),1):
   chunks.append(d);count+=diff
   if i%500==0:print('Text timestamp cohort',i,flush=True)
 p=pd.concat(chunks,ignore_index=True).merge(m[['item_id','whole_word_arm']],on='item_id');p['treat']=(p.whole_word_arm=='substitute').astype(float);p['daynum']=((p.day-pd.Timestamp('1970-01-01',tz='UTC')).dt.days).astype(int)
 p.to_parquet(ROOT/'revision/text_timestamp_panel.parquet',index=False)
 from fe_engine import scalar_report
 results=[]
 for name,data in [('unix_seconds',load_panel('full')),('text_date_assuming_explicit_UTC',p)]:
  for model in ['item_FE','TWFE']:results.append({'timestamp_basis':name,'model':model,**scalar_report(estimate(window(data),model))})
 pd.DataFrame(results).to_csv(ROOT/'tables/timestamp_sensitivity.csv',index=False)
 (ROOT/'audit/timestamp_event_period_audit.json').write_text(json.dumps({'selected_cohort_rows_with_different_dates_in_2017_02_08_through2020_01_27':count,'note':'Text+0 interpretation is an explicit sensitivity; correctness of either original field not independently established.'},indent=2))
 print('Event/2017-2019 calibration-range mismatched source dates:',count);print(pd.DataFrame(results).to_string(index=False))

"""Audit all raw CSVs and cache vectorized daily aggregation. Not final historical code."""
from pathlib import Path
import json,re,urllib.parse,hashlib,os
import numpy as np,pandas as pd
from concurrent.futures import ProcessPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
WEAR=('Factory New','Minimal Wear','Field-Tested','Well-Worn','Battle-Scarred')
TERMS=('Case','Capsule','Graffiti','Sticker','Package','Pin')
BAN=18197  # overridden from pandas below, not used as a hard-coded analysis date
BAN=(pd.Timestamp('2019-10-28')-pd.Timestamp('1970-01-01')).days
def classify(n,whole=False):
 if (bool(re.search(r'\bKey\b',n)) if whole else 'Key' in n):return 'key'
 if any(w in n for w in WEAR):return 'control_candidate'
 if any(t in n for t in TERMS):return 'substitute_candidate'
 return 'excluded'
def process(arg):
 idx,path=arg;p=Path(path);name=urllib.parse.unquote(p.stem.replace('_','%').split('___')[-1])
 d=pd.read_csv(p);nraw=len(d);badcols=not {'price','quantity','unix timestamp','date'}.issubset(d.columns)
 if badcols:raise ValueError(f'Unexpected schema {p} {list(d.columns)}')
 dups=int(d.duplicated().sum());tdup=int(d['unix timestamp'].duplicated().sum())
 num=d[['price','quantity','unix timestamp']].apply(pd.to_numeric,errors='coerce').astype(float);valid=num.notna().all(axis=1)
 num=num[valid];ts=num['unix timestamp'].to_numpy();days=np.floor_divide(ts,86400).astype(np.int32)
 dates=pd.to_datetime(d.loc[valid,'date'].str.slice(0,11),format='%b %d %Y',errors='coerce')
 date_days=((dates-pd.Timestamp('1970-01-01')).dt.days).to_numpy()
 out=num.assign(daynum=days,pq=num.price*num.quantity).groupby('daynum',sort=True).agg(units=('quantity','sum'),value=('pq','sum'),raw_rows=('quantity','size'))
 out['vwap']=out.value/out.units;out=out.drop(columns='value').reset_index();out=out[np.isfinite(out.vwap)]
 pre=out[out.daynum<BAN]
 rec={'item_id':idx,'file':p.name,'item':name,'historical_class':classify(name),'whole_word_class':classify(name,True),'raw_rows':nraw,'usable_raw_rows':len(num),'invalid_numeric_rows':int((~valid).sum()),'exact_duplicate_rows':dups,'duplicate_timestamps':tdup,'nonascending_timestamp_steps':int((np.diff(ts)<0).sum()),'negative_units':int((num.quantity<0).sum()),'zero_units_rows':int((num.quantity==0).sum()),'nonpositive_price':int((num.price<=0).sum()),'date_text_invalid':int(dates.isna().sum()),'date_text_unix_day_mismatch':int(np.sum(date_days!=days)),'subdaily_days':int((out.raw_rows>1).sum()),'first_day':int(out.daynum.min()) if len(out) else None,'last_day':int(out.daynum.max()) if len(out) else None,'observed_days':len(out),'internal_absent_days':int(out.daynum.max()-out.daynum.min()+1-len(out)) if len(out) else 0,'pre_n_obs':len(pre),'pre_med_price':pre.vwap.median(),'pre_med_units':pre.units.median(),'mean_raw_price':num.price.mean(),'all_med_units':out.units.median(),'container_case':name.endswith('Case'),'container_broad':any(t in name for t in ('Case','Capsule','Package')) and not any(w in name for w in WEAR),'decoded_example':name.lower()=='example price history'}
 # Add raw concentration sufficient statistics; no change to daily aggregation or selection.
 rec.update(recorded_units=float(num.quantity.sum()),recorded_value=float((num.price*num.quantity).sum()),
     price_gt100_units=float(num.loc[num.price>100,'quantity'].sum()),
     price_gt100_value=float((num.loc[num.price>100,'price']*num.loc[num.price>100,'quantity']).sum()),
     price_gt1000_rows=int((num.price>1000).sum()),price_max=float(num.price.max()))
 out['item_id']=np.int32(idx)
 return rec,out[['item_id','daynum','units','vwap','raw_rows']]
def main():
 if not (ROOT/'inputs/download_manifest.json').exists():raise RuntimeError('Download snapshot not yet sealed')
 files=sorted((ROOT/'inputs/download_snapshot/items').glob('*.csv'))
 cache=ROOT/'audit/daily_cache';cache.mkdir(exist_ok=True)
 meta=[];batch=[];chunk=0
 with ProcessPoolExecutor(max_workers=8) as ex:
  for i,(rec,daily) in enumerate(ex.map(process,enumerate(map(str,files)),chunksize=20),1):
   meta.append(rec);batch.append(daily)
   if i%500==0 or i==len(files):
    pd.concat(batch,ignore_index=True).to_parquet(cache/f'part_{chunk:03d}.parquet',index=False);batch=[];chunk+=1
   if i%1000==0:print('Audited',i,'of',len(files),flush=True)
 m=pd.DataFrame(meta);m.to_csv(ROOT/'audit/item_classification_and_quality.csv',index=False)
 old=set(json.loads((ROOT/'inputs/historical_raw_filenames.json').read_text()));new={p.name for p in files}
 totals={c:int(m[c].sum()) for c in ['raw_rows','usable_raw_rows','invalid_numeric_rows','exact_duplicate_rows','duplicate_timestamps','nonascending_timestamp_steps','negative_units','zero_units_rows','nonpositive_price','date_text_invalid','date_text_unix_day_mismatch','subdaily_days','observed_days','internal_absent_days']}
 totals.update({'raw_item_csvs':len(files),'old_raw_file_count':len(old),'present_new_missing_old':sorted(new-old),'present_old_missing_new':sorted(old-new),'historical_liquidity_cutoff':float(m.loc[m.historical_class!='excluded','pre_med_units'].quantile(.75)),'whole_word_classified_cutoff':float(m.loc[m.whole_word_class!='excluded','pre_med_units'].quantile(.75)),'all_item_corpus_cutoff':float(m.pre_med_units.quantile(.75)),'classification_changes':m.loc[m.historical_class!=m.whole_word_class,['item','historical_class','whole_word_class']].to_dict('records'),'example_file_at_root':(ROOT/'inputs/download_snapshot/example%20price%20history.csv').exists(),'example_inside_items':int(m.decoded_example.sum())})
 for version in ['historical','whole_word']:
  cl=m[f'{version}_class'];cut=totals[f'{version}_classified_cutoff'] if version=='whole_word' else totals['historical_liquidity_cutoff']
  arm=np.where(cl=='key','key',np.where((cl=='substitute_candidate')&(m.pre_med_price<10)&(m.pre_med_units>cut)&(m.pre_n_obs>=180),'substitute',np.where((cl=='control_candidate')&(m.pre_med_price>50)&(m.pre_n_obs>=180),'control','excluded')))
  # Original keys have at least one pre-period record, no 180-day restriction.
  arm=np.where(m.pre_n_obs>0,arm,'excluded');m[f'{version}_arm']=arm
 m.to_csv(ROOT/'audit/item_classification_and_quality.csv',index=False)
 totals['arm_counts']={v:m[f'{v}_arm'].value_counts().to_dict() for v in ['historical','whole_word']}
 totals['candidate_container_cases']=m.loc[(m.historical_arm=='substitute')&m.container_case,'item'].tolist()
 (ROOT/'audit/raw_audit.json').write_text(json.dumps(totals,indent=2))
 print(json.dumps({k:v for k,v in totals.items() if not isinstance(v,list)},indent=2),flush=True)
 print('RAW_AUDIT_COMPLETE',flush=True)
if __name__=='__main__':main()

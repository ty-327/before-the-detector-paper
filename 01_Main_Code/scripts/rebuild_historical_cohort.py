from pathlib import Path
import json,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv');names=set(json.loads((ROOT/'inputs/historical_selected_names.json').read_text()));ids=set(m.loc[m.item.isin(names),'item_id']);parts=[]
for f in sorted((ROOT/'audit/daily_cache').glob('*.parquet')):
 d=pd.read_parquet(f);parts.append(d[d.item_id.isin(ids)])
p=pd.concat(parts,ignore_index=True).merge(m[['item_id','item','historical_arm','historical_class']],on='item_id',validate='many_to_one').rename(columns={'historical_arm':'arm','historical_class':'group'});p['day']=pd.to_datetime(p.daynum,unit='D',utc=True)
for c in ['item','arm','group']:p[c]=p[c].astype('category')
p.to_parquet(ROOT/'historical/recovered_panel.parquet',index=False)
print('Reconstructed historical cohort from frozen names and raw data; not an original saved panel.')

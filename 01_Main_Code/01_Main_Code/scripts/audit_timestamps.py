from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import pandas as pd,numpy as np,json
ROOT=Path(__file__).resolve().parents[1]
def audit(path):
 d=pd.read_csv(path,usecols=['date','unix timestamp'])
 if d.empty:return {},[]
 parsed=pd.to_datetime(d.date.str.slice(0,14),format='%b %d %Y %H',utc=True)
 raw=pd.to_datetime(d['unix timestamp'],unit='s',utc=True)
 delta=(raw-parsed).dt.total_seconds().astype(int);counts=delta.value_counts().to_dict()
 ix=np.flatnonzero(delta.to_numpy()!=0)[:2]
 examples=[{'file':Path(path).name,'date_text':d.date.iloc[j],'unix_timestamp':int(d['unix timestamp'].iloc[j]),'parsed_unix_utc':str(raw.iloc[j]),'offset_seconds':int(delta.iloc[j])} for j in ix]
 return counts,examples
if __name__=='__main__':
 files=sorted((ROOT/'inputs/download_snapshot/items').glob('*.csv'));tot={};samples=[]
 with ProcessPoolExecutor(max_workers=8) as pool:
  for i,(counts,examples) in enumerate(pool.map(audit,map(str,files),chunksize=40),1):
   for k,v in counts.items():tot[int(k)]=tot.get(int(k),0)+int(v)
   if len(samples)<50:samples.extend(examples)
   if i%5000==0:print('Timestamp audit',i,flush=True)
 out={'unix_minus_text_seconds_counts':tot,'sample_disagreements':samples,'interpretation':'Historical implementation uses Unix seconds. Text timestamps explicitly show +0; disagreements are retained and text-date aggregation must be a separate sensitivity, not silently substituted.'}
 (ROOT/'audit/timestamp_audit.json').write_text(json.dumps(out,indent=2));print(json.dumps({'offset_counts':tot,'samples':samples[:4]},indent=2))

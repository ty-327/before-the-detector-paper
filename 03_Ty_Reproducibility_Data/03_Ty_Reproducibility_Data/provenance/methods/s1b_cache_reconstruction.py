"""Explicit reconstruction: vectorized audited daily cache; literal recovered S1b detection/report body.
Floating-point summation differs from np.average at about1e-13; strict boundary sensitivity is audited.
Original unmodified raw-data execution runs separately for numerical verification.
"""
from pathlib import Path
import ast,json,builtins,os,warnings,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
src=ROOT/'inputs/recovered/Old/s1b_analysis.py';tree=ast.parse(src.read_text(encoding='utf-8'))
g={'__name__':'reconstructed','__file__':str(src)}
exec(compile(ast.Module(body=[n for n in tree.body if not (isinstance(n,ast.If) and isinstance(n.test,ast.Compare))],type_ignores=[]),str(src),'exec'),g)
m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv');m['arm_s1b']=m.item.map(g['classify']);m=m[(m.arm_s1b!='excluded')&(m.usable_raw_rows>=30)&(m.observed_days>=30)].set_index('item_id')
historical_file_set='--historical-file-set' in sys.argv
if historical_file_set:
 missing=json.loads((ROOT/'audit/raw_audit.json').read_text())['present_new_missing_old']
 m=m[~m.file.isin(missing)]
series={};meta={};border=[]
for part in sorted((ROOT/'audit/daily_cache').glob('*.parquet')):
 d=pd.read_parquet(part);d=d[d.item_id.isin(m.index)]
 for item_id,v in d.groupby('item_id',sort=False):
  row=m.loc[item_id];name=row['item'];v=v.set_index(pd.to_datetime(v.daynum,unit='D',utc=True))[['units','vwap']];v.index.name='day';series[name]=v
  meta[name]={'arm':row.arm_s1b,'sub':g['subclass'](name) if row.arm_s1b=='fungible' else 'NF','mean_price':row.mean_raw_price,'med_units':row.all_med_units}
  r=v.vwap.pct_change();border.append({'item':name,'returns_within_1e_12_of_threshold':int((np.abs(r-1)<1e-12).sum()),'returns_within_1e_10_of_threshold':int((np.abs(r-1)<1e-10).sum())})
 print('Loaded cache',part.name,'eligible items',len(series),flush=True)
out=ROOT/('historical/s1b_cache_old_file_set' if historical_file_set else 'historical/s1b_cache_reconstruction');out.mkdir(exist_ok=True)
g.update({'series':series,'meta':meta,'HERE':str(out),'input':lambda *args:''})
main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
start=next(i for i,n in enumerate(main.body) if isinstance(n,ast.If) and isinstance(n.test,ast.UnaryOp) and isinstance(n.test.operand,ast.Name) and n.test.operand.id=='series')
# The first if contains function returns; series is nonempty, so begin at the following statement.
body=ast.Module(body=main.body[start+1:],type_ignores=[]);ast.fix_missing_locations(body)
warnings.filterwarnings('ignore');exec(compile(body,str(src),'exec'),g)
pd.DataFrame(border).to_csv(out/'s1b_float_threshold_boundary.csv',index=False)
(out/'SUCCESS.json').write_text(json.dumps({'status':'completed','classification':'historical substring','daily_aggregation':'vectorized reconstruction, not recovered final code'}))

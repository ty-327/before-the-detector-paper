"""Explicit reconstruction; source final concentration code has not been authenticated."""
import pandas as pd,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv')
units=m.recorded_units.sum();value=m.recorded_value.sum();rows=[]
def add(label,u,v,definition):rows.append(dict(measure=label,units=u,value_price_times_quantity=v,unit_percent=100*u/units,value_percent=100*v/value,definition=definition))
add('all_market',units,value,'All valid numeric rows of item CSVs; example excluded')
add('raw_record_price_gt100',m.price_gt100_units.sum(),m.price_gt100_value.sum(),'Strict price>100 at individual raw summary record')
q=m[m.mean_raw_price>100];add('item_mean_raw_price_gt100',q.recorded_units.sum(),q.recorded_value.sum(),'All records of items whose arithmetic mean raw price exceeds100')
q=m[m.item.str.contains(r'Knife|Bayonet|Karambit|Shadow Daggers',regex=True)];add('knife_family',q.recorded_units.sum(),q.recorded_value.sum(),'Literal name families Knife, Bayonet, Karambit or Shadow Daggers')
q=m.nlargest(100,'recorded_value');add('top100_value_items',q.recorded_units.sum(),q.recorded_value.sum(),'Top100 item files by sum(raw price*quantity)')
pd.DataFrame(rows).to_csv(ROOT/'tables/concentration_reconstruction.csv',index=False)
q[['item','recorded_units','recorded_value']].to_csv(ROOT/'tables/concentration_top100_items.csv',index=False)
out={'items_with_raw_price_gt1000':int((m.price_gt1000_rows>0).sum()),'raw_records_price_gt1000':int(m.price_gt1000_rows.sum()),'status':'new reconstruction; not authenticated final historical implementation','currency':'Raw has no currency column; no conversion; USD manuscript attribution remains documentary','value_measure':'Sum of reported price summaries multiplied by reported quantities; not transaction-level value independently verified'}
(ROOT/'tables/concentration_high_price_counts.json').write_text(json.dumps(out,indent=2))
print(pd.DataFrame(rows).to_string(index=False));print(json.dumps(out),flush=True)

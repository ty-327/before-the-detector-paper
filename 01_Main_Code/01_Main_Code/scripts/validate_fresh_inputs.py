"""Identity, membership and boundary checks on newly reconstructed inputs."""
from pathlib import Path
import json, hashlib
import numpy as np,pandas as pd
from revision_models import ROOT,EN,load_panel,window
m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv');c=pd.read_csv(ROOT/'revision/container_definitions.csv')
joined=c.merge(m[['item_id','item']],on='item_id',suffixes=('_frozen','_fresh'),validate='one_to_one')
assert len(joined)==len(c) and (joined.item_frozen==joined.item_fresh).all(), 'Frozen IDs do not map to same raw names'
names=set(json.loads((ROOT/'inputs/historical_selected_names.json').read_text()))
assert names<=set(m.item),'Historical name list missing from raw snapshot'
p=load_panel('full');d=window(p)
assert not p.duplicated(['item_id','daynum']).any()
assert (d.daynum.min(),d.daynum.max())==(EN-21,EN+20)
assert d[d.daynum<EN].daynum.nunique()==21 and d[d.daynum>=EN].daynum.nunique()==21
assert pd.Timestamp('2019-11-18',tz='UTC') not in set(d.day)
meta={'status':'PASS','container_rows_validated':len(c),'historical_names':len(names),'window_rows':len(d),
      'window_start':str(d.day.min()),'window_end':str(d.day.max()),'observed_days':int(d.daynum.nunique()),
      'candidate_items':int(d[d.treat==1].item_id.nunique()),'control_items':int(d[d.treat==0].item_id.nunique()),
      'missing_cells_not_filled':int(d.item_id.nunique()*42-len(d)),
      'selected_membership':m[m.whole_word_arm!='excluded'][['item','whole_word_arm']].to_dict('records')}
(ROOT/'audit/FRESH_INPUT_CHECKS.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print({k:v for k,v in meta.items() if k!='selected_membership'},flush=True)

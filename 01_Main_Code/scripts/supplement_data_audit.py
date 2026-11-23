from pathlib import Path
import json,re,urllib.parse,zipfile,hashlib
from xml.etree import ElementTree as ET
import numpy as np,pandas as pd
from revision_models import ROOT,EN
m=pd.read_csv(ROOT/'audit/item_classification_and_quality.csv');conv=pd.read_csv(ROOT/'inputs/download_snapshot/name_conversion_table.csv');encoded,decoded=conv.columns[:2]
lookup=dict(zip(conv[encoded],conv[decoded]));m['simple_percent_decode']=m.file.map(lambda s:urllib.parse.unquote(s[:-4]));m['conversion_table_decoded']=m.file.map(lambda s:lookup.get(s[:-4]))
conversion_names=set(conv[decoded]);m['name_in_conversion_table']=m.item.isin(conversion_names);m['decode_changes_if_underscores_preserved']=m.item!=m.simple_percent_decode
for c in ['first_day','last_day']:m[c+'_UTC']=pd.to_datetime(m[c],unit='D',utc=True).astype(str)
def reasons(r):
 out=[]
 if r.raw_rows==0:out.append('empty_history')
 if r.pre_n_obs==0:out.append('no_pre_intervention_history')
 if r.whole_word_class=='key':out.append('key_separate_from_H2')
 elif r.whole_word_class=='excluded':out.append('unclassified_category')
 else:
  if r.pre_n_obs<180:out.append('fewer_than180_observed_pre_days')
  if r.whole_word_class=='substitute_candidate':
   if not r.pre_med_price<10:out.append('candidate_price_not_below10')
   if not r.pre_med_units>36:out.append('candidate_liquidity_not_above_computed36')
  elif not r.pre_med_price>50:out.append('control_price_not_above50')
 return '|'.join(out) or 'eligible'
m['eligibility_reason']=m.apply(reasons,axis=1);m.to_csv(ROOT/'corrected_analysis/item_classification_audit.csv',index=False)
units=0.;first=np.inf;last=-np.inf
for part in sorted((ROOT/'audit/daily_cache').glob('*.parquet')):
 d=pd.read_parquet(part,columns=['units','daynum']);units+=d.units.sum();first=min(first,d.daynum.min());last=max(last,d.daynum.max())
example=pd.read_csv(ROOT/'inputs/download_snapshot/example%20price%20history.csv');blue=pd.read_csv(ROOT/'inputs/download_snapshot/items/%27Blueberries%27%20Buckshot%20%7C%20NSWC%20SEAL.csv');match=example.merge(blue.drop_duplicates(),on=list(example.columns),how='left',indicator=True)
names=conv[decoded].astype(str);summary={'zip_path':'User-supplied archive; see inputs/download_manifest.json','item_files':len(m),'unique_legacy_decoded_names':m.item.nunique(),'legacy_decoded_name_collisions':int(m.item.duplicated().sum()),'name_table_rows':len(conv),'name_table_unique':conv[decoded].nunique(),'names_missing_from_conversion_table':m.loc[~m.name_in_conversion_table,'item'].tolist(),'literal_underscore_decoder_changes':m.loc[m.decode_changes_if_underscores_preserved,['file','item','simple_percent_decode']].to_dict('records'),'empty_item_files':m.loc[m.raw_rows==0,'file'].tolist(),'recorded_rows':int(m.raw_rows.sum()),'recorded_units':int(units),'date_min_unix_UTC':str(pd.to_datetime(first,unit='D',utc=True)),'date_max_unix_UTC':str(pd.to_datetime(last,unit='D',utc=True)),'name_table_substring_Key_matches':int(names.str.contains('Key',regex=False).sum()),'name_table_whole_word_Key_matches':int(names.str.contains(r'\bKey\b').sum()),'example_rows':len(example),'blueberries_rows':len(blue),'example_exact_row_matches':int((match._merge=='both').sum()),'example_unmatched_rows':int((match._merge!='both').sum()),'example_is_exact_prefix':bool(example.equals(blue.iloc[:len(example)].reset_index(drop=True))),'manuscript_data_card_comparators':{'items':22492,'rows':99348409,'units':5764583111},'interpretation':'Daily weighted price is a quantity-weighted mean of source price-window summaries; without trade records and interval definitions it is not authenticated trade-level VWAP. Duplicate Unix timestamps with different data are retained; overlapping interval volume cannot be ruled out from absent start/end fields. USD is manuscript-reported, not authenticated by an explicit raw currency field.'}
summary['difference_from_manuscript_data_card']={'items':len(m)-22492,'rows':int(m.raw_rows.sum())-99348409,'units':int(units)-5764583111}
(ROOT/'audit/supplemental_data_audit.json').write_text(json.dumps(summary,indent=2))
plans=[]
for p in (ROOT/'inputs/recovered').rglob('*.docx'):
 if not any(n in p.name for n in ['PreRegistration','Prespecification','COSE_KeyBan_Plan','COSE_Signature_Plan']):continue
 with zipfile.ZipFile(p) as z:
  x=ET.fromstring(z.read('docProps/core.xml'));props={v.tag.split('}')[-1]:v.text for v in x}
 plans.append({'file':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'properties':props,'timestamp_status':'Embedded metadata only; not independently authenticated or a public registration timestamp'})
(ROOT/'audit/plan_embedded_metadata.json').write_text(json.dumps(plans,indent=2))
print(json.dumps(summary,indent=2));print('PLAN_METADATA',json.dumps(plans,indent=2))

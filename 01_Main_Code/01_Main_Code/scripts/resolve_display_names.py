"""Resolve 16 damaged display characters explicitly; never change item IDs or eligibility."""
import json,pandas as pd
from revision_models import ROOT
from audit_raw import classify
m=pd.read_csv(ROOT/'corrected_analysis/item_classification_audit.csv');c=pd.read_csv(ROOT/'inputs/download_snapshot/name_conversion_table.csv')
m['resolved_display_name']=m.conversion_table_decoded.fillna(m.simple_percent_decode);m['resolution']='Exact encoded-name conversion-table lookup'
rows=[]
for ix,r in m[m.conversion_table_decoded.isna()].iterrows():
 candidates=c[c.iloc[:,0].str.replace('\u00f6','\ufffd',regex=False)==r.file[:-4]]
 assert len(candidates)==1,(r.file,len(candidates))
 name=candidates.iloc[0,1];assert classify(name,True)==r.whole_word_class
 m.loc[ix,'resolved_display_name']=name;m.loc[ix,'resolution']='Explicit unique correspondence: damaged U+FFFD filename character maps to conversion-table U+00F6; no record relabelling or item-ID merge'
 rows.append({'item_id':int(r.item_id),'file':r.file,'legacy_name':r['item'],'resolved_name':name,'H2_arm':r.whole_word_arm})
assert m.resolved_display_name.nunique()==len(m)
m[['item_id','file','item','resolved_display_name','resolution']].to_csv(ROOT/'corrected_analysis/resolved_display_names.csv',index=False)
(ROOT/'audit/display_name_resolution.json').write_text(json.dumps({'explicit_character_repairs':rows,'literal_underscore_repairs':int(m.decode_changes_if_underscores_preserved.sum()),'all_names_uniquely_resolved':True,'eligibility_unchanged':True,'statement':'Original filenames, original name table and executed statistical outputs preserved. Display-name repairs are a separate evidence mapping.'},indent=2))
print('Resolved16 replacement-character names and29 underscore names; eligibility unchanged.')

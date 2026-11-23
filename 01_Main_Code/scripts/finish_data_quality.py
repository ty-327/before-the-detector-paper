from pathlib import Path
import json,urllib.parse,numpy as np,pandas as pd
from revision_models import ROOT,EN,load_panel,group_subset,window
m=pd.read_csv(ROOT/'corrected_analysis/item_classification_audit.csv');m['canonical_name']=m.conversion_table_decoded.fillna(m.simple_percent_decode)
cases={
'Chroma 2 Case':'Chroma 2 Case Key','Chroma 3 Case':'Chroma 3 Case Key','Chroma Case':'Chroma Case Key','Clutch Case':'Clutch Case Key',
'CS:GO Weapon Case 2':'CS:GO Case Key','CS:GO Weapon Case 3':'CS:GO Case Key','CS:GO Weapon Case':'CS:GO Case Key','Danger Zone Case':'Danger Zone Case Key',
'eSports 2013 Case':'eSports Key','eSports 2013 Winter Case':'eSports Key','eSports 2014 Summer Case':'eSports Key','Falchion Case':'Falchion Case Key',
'Gamma 2 Case':'Gamma 2 Case Key','Gamma Case':'Gamma Case Key','Glove Case':'Glove Case Key','Horizon Case':'Horizon Case Key','Huntsman Weapon Case':'Huntsman Case Key',
'Operation Bravo Case':'CS:GO Case Key','Operation Breakout Weapon Case':'Operation Breakout Case Key','Operation Hydra Case':'Operation Hydra Case Key','Operation Phoenix Weapon Case':'Operation Phoenix Case Key','Operation Vanguard Weapon Case':'Operation Vanguard Case Key','Operation Wildfire Case':'Operation Wildfire Case Key','Prisma Case':'Prisma Case Key','Revolver Case':'Revolver Case Key','Shadow Case':'Shadow Case Key','Spectrum 2 Case':'Spectrum 2 Case Key','Spectrum Case':'Spectrum Case Key','Winter Offensive Weapon Case':'Winter Offensive Case Key'}
c=pd.read_csv(ROOT/'revision/container_definitions.csv');assert set(c[c.key_dependent_case].item)==set(cases)
keys=set(m.loc[m.whole_word_arm=='key','canonical_name']);assert set(cases.values())<=keys
c['explicit_case_whitelist_match']=c.item.isin(cases);c['associated_key']=c.item.map(cases);c['key_name_present_in_raw_corpus']=c.associated_key.isin(keys)
c['validation_basis']=np.where(c.explicit_case_whitelist_match,'Explicit item-by-item case/key mapping; names checked against source conversion table; same frozen membership','Not on the explicit weapon-case whitelist; broad container flag separately retained')
c['primary_reference']=c.associated_key.map(lambda s:'https://steamcommunity.com/market/listings/730/'+urllib.parse.quote(s,safe='') if isinstance(s,str) else '')
c.to_csv(ROOT/'corrected_analysis/container_item_validation.csv',index=False)
raw=pd.read_parquet(ROOT/'historical/full_zip_panel_vectorized.parquet');kr=raw[(raw.whole_word_arm=='key')&raw.daynum.between(EN-21,EN-1)].units.sum();p=load_panel('full');rows=[]
for group in ['all','exclude_cases','exclude_broad']:
 d=window(group_subset(p,group));pre=d[(d.treat==1)&(d.daynum<EN)];den=pre.units.sum()
 rows.append({'candidate_group':group,'start':'2019-10-07','end_inclusive':'2019-10-27','keys':27,'candidate_nominated':int(group_subset(p,group).query('treat==1').item_id.nunique()),'candidate_observed_in_pre':pre.item_id.nunique(),'pre21_candidate_units':den,'pre21_recorded_key_units':kr,'key_to_candidate_percent':100*kr/den,'interpretation':'Recorded marketplace turnover; not an estimate of illicit flow'})
pd.DataFrame(rows).to_csv(ROOT/'tables/matched_key_flow_scales.csv',index=False)
dups=[]
for r in m[m.duplicate_timestamps>0].itertuples():
 d=pd.read_csv(ROOT/'inputs/download_snapshot/items'/r.file);x=d[d['unix timestamp'].duplicated(keep=False)]
 for ts,g in x.groupby('unix timestamp'):
  dups.append({'item_id':r.item_id,'item':r.canonical_name,'timestamp':ts,'rows':len(g),'distinct_prices':g.price.nunique(),'distinct_quantities':g.quantity.nunique(),'distinct_written_dates':g.date.nunique(),'units_retained':g.quantity.sum(),'interpretation':'Nonidentical same-timestamp records retained by legacy aggregation; interval overlap cannot be established'})
pd.DataFrame(dups).to_csv(ROOT/'corrected_analysis/conflicting_timestamp_groups.csv',index=False)
cut=m.loc[(m.historical_class!='excluded')&(m.pre_n_obs>0),'pre_med_units']
out={'empty_item_files':int((m.raw_rows==0).sum()),'conversion_table_mapping_complete':bool(m.conversion_table_decoded.notna().all()),'canonical_name_unique':int(m.canonical_name.nunique()),'canonical_vs_legacy_changes':int((m.canonical_name!=m.item).sum()),'liquidity_population_items':len(cut),'liquidity_cutoff':cut.quantile(.75),'liquidity_population':'Items categorized by the recovered key code as key, fungible or wear-designated nonfungible, with at least one observed day before nominal event. Percentile of item-specific median daily quantities, before price, history-length or liquidity selection. pandas linear quantile.','liquidity_interval':'All available history from 2013-04-26 through 2019-10-27 inclusive; item-specific coverage differs','timestamp_duplicate_groups':len(dups),'timestamp_duplicate_rows':sum(r['rows'] for r in dups),'timestamp_duplicate_excess':sum(r['rows']-1 for r in dups),'same_timestamp_groups_different_prices':sum(r['distinct_prices']>1 for r in dups),'same_timestamp_groups_different_quantities':sum(r['distinct_quantities']>1 for r in dups),'interval_overlap_status':'Unknown. No interval start/end or trade identifiers are supplied; summing all positive quantities reproduces the source implementation but cannot authenticate nonoverlap.','currency_status':'No currency field; USD attribution is manuscript/dataset documentation, not independently authenticated row-wise. No conversion performed.','case_mapping_status':'Explicit29-case whitelist and associated24key names agree exactly with frozen exclusion; not a post-result membership adjustment. Steam primary pages support key families; mapped page URLs retained for review.','data_transform_description':'Daily sum of recorded quantities; quantity-weighted mean of window median price summaries, not authenticated transaction VWAP.'}
(ROOT/'audit/final_data_quality.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2));print(pd.DataFrame(rows).to_string(index=False))

"""Post-execution comparison of v48 S3.8 audit facts and historical cohort structure."""
from pathlib import Path
import argparse,json
import pandas as pd
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',type=Path,required=True);ap.add_argument('--reference',type=Path,required=True);a=ap.parse_args();run=a.run;ref=a.reference/'supplementary/provenance';rows=[]
 def compare(label,e,g):
  if isinstance(e,dict):
   for k,v in e.items():compare(label+'.'+k,v,g.get(k) if isinstance(g,dict) else None)
  else:rows.append({'field':label,'matches':e==g,'expected':json.dumps(e,ensure_ascii=False),'actual':json.dumps(g,ensure_ascii=False)})
 for name in ['raw_audit.json','final_data_quality.json','timestamp_audit.json']:
  compare(name,json.loads((ref/name).read_text(encoding='utf-8')),json.loads((run/'audit'/name).read_text(encoding='utf-8')))
 e=json.loads((ref/'recovered_panel_audit.json').read_text(encoding='utf-8'));p=pd.read_parquet(run/'historical/recovered_panel.parquet')
 g={'rows':len(p),'items':p.item.nunique(),'date_min':str(p.day.min()),'date_max':str(p.day.max()),'duplicates_item_day':int(p.duplicated(['item','day']).sum()),'negative_units':int((p.units<0).sum()),'zero_units':int((p.units==0).sum()),'arm_items':p.groupby('arm',observed=True).item.nunique().to_dict(),'missing_cells':{c:int(p[c].isna().sum()) for c in ['day','units','vwap','item','group','arm']}}
 for k,v in g.items():compare('historical_cohort.'+k,e[k],v)
 if 'historical_key_names' in e:compare('historical_cohort.key_names',sorted(e['historical_key_names']),sorted(p.loc[p.arm=='key','item'].astype(str).unique()))
 d=pd.DataFrame(rows);d.to_csv(run/'comparison/V48_AUDIT_COMPARISON.csv',index=False)
 status={'checks':len(rows),'differences':int((~d.matches).sum()),'status':'MATCH' if d.matches.all() else 'DIFFERENCES_REPORTED'}
 (run/'comparison/AUDIT_COMPARISON_STATUS.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
if __name__=='__main__':main()

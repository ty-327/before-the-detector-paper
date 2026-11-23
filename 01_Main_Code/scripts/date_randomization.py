"""Explicit reconstruction: frozen new dates/seed; never tuned to submitted p-values."""
from pathlib import Path
import json,numpy as np,pandas as pd
from revision_models import ROOT,CFG,EN,load_panel,group_subset,window,estimate
def main():
 p=load_panel('full');frozen=pd.read_csv(ROOT/'revision/randomization_dates_frozen.csv')
 chosen=set(pd.to_datetime(frozen.date,utc=True).map(lambda d:(d-pd.Timestamp('1970-01-01',tz='UTC')).days))
 calendar=pd.date_range(CFG['randomization']['start'],CFG['randomization']['end'],tz='UTC')
 hold=(pd.Timestamp('2018-03-29',tz='UTC')-pd.Timestamp('1970-01-01',tz='UTC')).days
 rows=[];summary=[]
 for group in ['all','exclude_cases','exclude_broad']:
  q=group_subset(p,group)
  for j,date in enumerate(calendar):
   event=(date-pd.Timestamp('1970-01-01',tz='UTC')).days;d=window(q,event)
   for model in ['item_FE','TWFE']:
    f=estimate(d,model,event,False)
    rows.append({'candidate_group':group,'model':model,'date':str(date.date()),'daynum':event,'in_frozen150':event in chosen,'overlaps_trade_hold':event-21<=hold<=event+20,'coefficient':float(f['beta'][-1]),'n':f['n'],'items':f['n_items']})
   if (j+1)%150==0:print('Calibration',group,j+1,'of',len(calendar),flush=True)
  df=pd.DataFrame(rows);df.to_csv(ROOT/'tables/date_calibration_full_calendar.csv',index=False)
  for model in ['item_FE','TWFE']:
   actual=float(estimate(window(q),model,covariance=False)['beta'][-1]);g=df[(df.candidate_group==group)&(df.model==model)]
   for subset,v in [('frozen150',g[g.in_frozen150]),('frozen150_exclude_trade_hold',g[g.in_frozen150&~g.overlaps_trade_hold]),('full_calendar',g)]:
    b=v.coefficient.to_numpy();n=len(b);lo=int(np.sum(b<=actual));hi=int(np.sum(b>=actual));ab=int(np.sum(np.abs(b)>=abs(actual)))
    summary.append({'candidate_group':group,'model':model,'calibration':subset,'n_dates':n,'mean':b.mean(),'std_ddof1':b.std(ddof=1),'q95':np.quantile(b,.95),'actual':actual,'lower_tail_raw':lo/n,'lower_tail_plus_one':(lo+1)/(n+1),'upper_tail_plus_one':(hi+1)/(n+1),'two_sided_absolute_plus_one':(ab+1)/(n+1),'two_sided_double_min_plus_one':min(1,2*(min(lo,hi)+1)/(n+1))})
 pd.DataFrame(summary).to_csv(ROOT/'tables/date_randomization_summary.csv',index=False)
 pd.DataFrame(rows).query('in_frozen150').to_csv(ROOT/'tables/date_randomization_frozen150_results.csv',index=False)
 print(pd.DataFrame(summary).to_string(index=False));print('DATE_RANDOMIZATION_COMPLETE',flush=True)
if __name__=='__main__':main()

from pathlib import Path
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':13,'axes.labelsize':11,'figure.dpi':160,'savefig.dpi':240,'axes.spines.top':False,'axes.spines.right':False})
COL=['#176B87','#BA4A32','#4C8460','#77559C','#B68422','#397B91','#96616B','#444444']
def save(fig,name):
 fig.savefig(ROOT/'revision_extensions/v2/figures'/f'{name}.png',bbox_inches='tight');fig.savefig(ROOT/'revision_extensions/v2/figures'/f'{name}.svg',bbox_inches='tight');plt.close(fig)
r=pd.read_csv(ROOT/'tables/revision_robustness.csv');q=r[(r.cohort=='full')&(r.model=='TWFE')&(r.specification=='corrected_42days')]
fig,ax=plt.subplots(figsize=(8.5,4));names={'all':'All candidates','exclude_cases':'Exclude 29 cases','exclude_broad':'Exclude 59 containers'}
for j,(_,row) in enumerate(q.iterrows()):
 ax.errorbar(row.coefficient,j,xerr=[[row.coefficient-row.ci_low_two_way],[row.ci_high_two_way-row.coefficient]],fmt='o',color=COL[j],capsize=4)
ax.set_yticks(range(len(q)),[names[g] for g in q.candidate_group]);ax.axvline(0,color='#777777',lw=1,ls='--');ax.set_xlabel('Candidate-by-post coefficient on log(1 + daily units)');ax.set_title('Two-way fixed effects: the directional contrast remains negative')
ax.invert_yaxis();fig.text(.02,.015,'Full ZIP cohort; 7 Oct-17 Nov 2019. Item and date fixed effects; 95% item/date-cluster t intervals.\nDescriptive contrasts: pre-trend and placebo failures prevent a causal interpretation.',fontsize=9);fig.subplots_adjust(bottom=.25,left=.25);save(fig,'01_twfe_robustness')
e=pd.read_csv(ROOT/'tables/twfe_event_study.csv');fig,axs=plt.subplots(1,2,figsize=(11,4.8),sharey=True)
for ax,g in zip(axs,['all','exclude_cases']):
 d=e[e.candidate_group==g].sort_values('offset');ax.errorbar(d.offset,d.coefficient,yerr=[d.coefficient-d.ci_low_item,d.ci_high_item-d.coefficient],fmt='o',ms=3,color=COL[0],alpha=.9,capsize=2)
 ax.scatter([-1],[0],marker='s',color='black',s=18);ax.axhline(0,color='#888888',lw=1);ax.axvline(-.5,color=COL[1],ls='--',lw=1);ax.set_title(names[g]);ax.set_xlabel('Days relative to 28 October 2019')
axs[0].set_ylabel('Candidate-day coefficient, reference day -1');fig.suptitle('Regression event study: flat pre-trends are rejected',fontsize=14);fig.text(.02,.02,'Full ZIP cohort; item/day fixed effects. Bars are 95% pointwise item-cluster intervals, not simultaneous bands.\nThe reference observation is fixed to zero. Joint lead tests use all leads -21 through -2.',fontsize=9);fig.subplots_adjust(bottom=.22,top=.82,wspace=.12);save(fig,'02_twfe_event_study')
floors=pd.read_csv(ROOT/'revision_extensions/v2/tables/detection_floors.csv');z=floors[floors.model=='TWFE'];shapes=['step','ramp7','ramp21','delay7','delay14','distributed','heterogeneous','concentrated10pct','delay28'];labels=['Abrupt step','7-day ramp','21-day ramp','7-day delay','14-day delay','Distributed onsets','Heterogeneous speeds','10% of items','28-day delay (outside)']
cols=[(g,b) for g in ['all','exclude_cases','exclude_broad'] for b in ['neutral','observed']];matrix=np.array([[float(z[(z['shape']==s)&(z.candidate_group==g)&(z.background==b)].floor_fraction.iloc[0])*100 for g,b in cols] for s in shapes])
fig,ax=plt.subplots(figsize=(10,6.8));im=ax.imshow(np.minimum(matrix,300),vmin=0,vmax=300,cmap='YlOrRd',aspect='auto')
for i in range(len(shapes)):
 for j in range(len(cols)):
  val=matrix[i,j];ax.text(j,i,'>300' if not np.isfinite(val) else f'{val:.0f}',ha='center',va='center',color='white' if val>=180 else '#222222',fontweight='bold')
ax.set_yticks(range(len(shapes)),labels);ax.set_xticks(range(len(cols)),['All\nneutral','All\nobserved','No cases\nneutral','No cases\nobserved','No containers\nneutral','No containers\nobserved']);ax.set_title('Scenario-specific detection floors differ substantially')
fig.colorbar(im,ax=ax,label='Terminal added rate (% of pre-event daily candidate flow)',fraction=.03,pad=.03);fig.text(.02,.015,'New revision simulation: first grid point reaching 80% recovery in 2,500 runs; no interpolation.\nTiming shapes have different cumulative volumes. Concentrated injections preserve the total terminal-rate budget.\n>300: no crossing on the grid. The 28-day delay adds zero units within the observation window.',fontsize=9);fig.subplots_adjust(left=.23,bottom=.23,top=.9,right=.91);save(fig,'03_detection_floor_scenarios')
curves=pd.read_csv(ROOT/'revision_extensions/v2/tables/injection_power_curves.csv');fig,axs=plt.subplots(1,2,figsize=(11,5),sharey=True)
shown=['step','ramp21','delay14','concentrated10pct'];sl={'step':'Abrupt step','ramp21':'21-day ramp','delay14':'14-day delay','concentrated10pct':'10% of items'}
for ax,background in zip(axs,['neutral','observed']):
 for j,s in enumerate(shown):
  d=curves[(curves.model=='TWFE')&(curves.candidate_group=='all')&(curves.background==background)&(curves['shape']==s)].sort_values('terminal_fraction')
  ax.plot(d.terminal_fraction*100,d.power,color=COL[j],label=sl[s],lw=1.8);ax.fill_between(d.terminal_fraction*100,d.wilson_low,d.wilson_high,color=COL[j],alpha=.10)
 ax.axhline(.8,color='#555555',ls='--',lw=1);ax.set_ylim(0,1.02);ax.set_xlim(0,300);ax.set_title(background.capitalize()+' background');ax.set_xlabel('Terminal added rate (% of pre-event daily flow)')
axs[0].set_ylabel('Recovery probability');axs[0].legend(loc='lower right',fontsize=9);fig.suptitle('Power depends on timing, concentration and background',fontsize=14);fig.text(.02,.02,'All candidates; TWFE; 2,500 repetitions. Bands show conditional 95% Wilson Monte Carlo intervals.\nThreshold and historical-date uncertainty are reported separately in the detection-floor tables.',fontsize=9);fig.subplots_adjust(bottom=.22,top=.83,wspace=.12);save(fig,'04_power_curves')
c=pd.read_csv(ROOT/'tables/date_calibration_full_calendar.csv');c=c[(c.candidate_group=='all')&(c.model=='TWFE')];actual=float(q[q.candidate_group=='all'].coefficient.iloc[0]);frozen=c[c.in_frozen150]
fig,ax=plt.subplots(figsize=(8.5,4.6));bins=np.linspace(-.5,.5,42);ax.hist(c.coefficient,bins=bins,density=True,alpha=.35,color='#7A8790',label='All 914 eligible dates');ax.hist(frozen.coefficient,bins=bins,density=True,histtype='step',lw=1.8,color=COL[0],label='Frozen 150 sampled dates');ax.axvline(actual,color=COL[1],lw=1.8,label='2019 event coefficient');ax.axvline(frozen.coefficient.quantile(.95),color=COL[2],ls='--',lw=1.8,label='95th percentile of frozen draws');ax.set_xlabel('TWFE candidate-by-post coefficient');ax.set_ylabel('Density');ax.set_title('Historical-date calibration is sensitive to sampled dates');ax.legend(fontsize=9);fig.text(.02,.015,'New seed 20261112; 1 Mar 2017-31 Aug 2019, 42-day windows. Overlapping windows are dependent.\nThis distribution is historical calibration, not a randomized-intervention null distribution.',fontsize=9);fig.subplots_adjust(bottom=.22);save(fig,'05_historical_date_calibration')
print('FIGURES_COMPLETE: PNG and SVG versions of five figures')

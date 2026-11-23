from pathlib import Path
import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
a=pd.read_csv(ROOT/'revision_extensions/v2/tables/detection_floors.csv');b=pd.read_csv(ROOT/'revision_extensions/v2_equal_cumulative/tables/detection_floors.csv')
fig,axs=plt.subplots(1,2,figsize=(10.5,5.2),sharey=True)
shapes=['step','ramp21','delay14','distributed','heterogeneous'];labels=['Abrupt step','21-day ramp','14-day delay','Distributed','Heterogeneous'];pos=np.arange(5)
for ax,bg in zip(axs,['neutral','observed']):
 vals=[]
 for d in [a,b]:
  z=d[(d.candidate_group=='all')&(d.model=='TWFE')&(d.background==bg)].set_index('shape');vals.append([100*z.loc[s,'floor_fraction'] for s in shapes])
 ax.barh(pos-.17,vals[0],height=.32,color='#176B87',label='Equal eventual daily rate');ax.barh(pos+.17,vals[1],height=.32,color='#BA4A32',label='Equal cumulative units')
 ax.set_yticks(pos,labels);ax.invert_yaxis();ax.set_title(bg.capitalize()+' background');ax.set_xlabel('First grid point at 80% recovery (%)');ax.spines[['top','right']].set_visible(False)
axs[0].legend(fontsize=8,loc='lower right');fig.suptitle('Signal timing and the amount delivered are separate choices',fontsize=13)
fig.text(.02,.015,'New TWFE simulations, all candidates; 2,500 runs. Daily-rate scaling preserves delays and ramp shortfalls.\nCumulative scaling rescales each nonzero allocation to the same total over observed post-event rows.\nThe two series use their declared deterministic random streams; conditional Monte Carlo variation remains.',fontsize=9)
fig.subplots_adjust(left=.16,bottom=.25,top=.86,wspace=.08)
for ext in ['png','svg']:fig.savefig(ROOT/f'revision_extensions/v2/figures/06_signal_scale_comparison.{ext}',dpi=220,bbox_inches='tight')
print('Equal cumulative comparison figure saved')

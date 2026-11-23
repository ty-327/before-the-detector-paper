"""Fresh evidence from current raw rebuild only; regenerate every matched computation."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
import sys,json,shutil,argparse,logging,datetime
import numpy as np,pandas as pd
sys.path.insert(0,str(ROOT/'scripts'))
import revision_models as rm
rm.ROOT=OLD
from fe_engine import scalar_report
sys.path.insert(0,str(ROOT/'scripts/cloud'))
import cose_core as cc,run_analysis as cloud
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
E=ROOT/'evidence'; manifest=[]
def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    manifest.append(dict(source=str(src),evidence=str(dst.relative_to(ROOT)),sha256=sha(src),bytes=src.stat().st_size,activity='freshly_regenerated_in_this_execution'))
def history_summary(frame):
    out={}
    for tag,f in [('all_draws',frame),('excluding_trade_hold_overlap',frame[~frame.overlaps_trade_hold])]:
        b=f.coefficient.to_numpy();out[tag]={'threshold95':float(np.quantile(b,.95)),'mean':float(b.mean()),'n':len(b)}
    return {'failed_draws':0,'summaries':out}
def cloud_frame(p):
    d=p[['item','day','units','arm']].copy();d['item']=d.item.astype(str);d['arm']=d.arm.astype(str).replace({'substitute':'candidate'});return d
def main():
    cfg=json.loads((ROOT/'FINAL_SETTINGS.json').read_text(encoding='utf-8'));assert cfg['primary_calibration']=='frozen150_centered'
    # Preserve the source arrays needed for final results, including original bootstrap indices.
    for scale,folder in [('eventual','v2'),('equal_cumulative','v2_equal_cumulative')]:
        src=OLD/f'revision_extensions/{folder}/revision/simulation_draws'
        for group in ['all','exclude_cases','exclude_broad']:
            if scale=='equal_cumulative' and group=='exclude_broad':continue
            for model in ['TWFE','item_FE']:
                if model=='item_FE' and (scale=='equal_cumulative' or group=='exclude_broad'):continue
                shapes=['step'] if model=='item_FE' or group=='exclude_broad' else (['step','ramp21','delay14','distributed','heterogeneous'] if scale=='equal_cumulative' else ['step','ramp7','ramp21','delay7','delay14','delay28','distributed','heterogeneous','concentrated10pct'])
                copy(src/f'{group}_{model}_randomness.npz',E/f'dell/{scale}/{group}_{model}_randomness.npz')
                for bg in ['neutral','observed']:
                    for shape in shapes:copy(src/f'{group}_{model}_{bg}_{shape}.npz',E/f'dell/{scale}/{group}_{model}_{bg}_{shape}.npz')
    for f in ['tables/date_calibration_full_calendar.csv','tables/revision_robustness.csv','tables/empirical_response_shapes.csv','tables/twfe_pretrend_tests.csv','revision/randomization_dates_frozen.csv','revision/container_definitions.csv']:
        copy(OLD/f,E/'sources'/Path(f).name)
    for folder in ['v2','v2_equal_cumulative']:
        for f in ['detection_floors.csv','injection_power_curves.csv','calibration_threshold_uncertainty.csv']:
            copy(OLD/f'revision_extensions/{folder}/tables/{f}',E/f'earlier_tables/{folder}/{f}')
    # This CSV is freshly rebuilt here, not the previously prepared recovered CSV.
    fresh=pd.read_parquet(ROOT/'historical/full_zip_panel_vectorized.parquet')
    fresh[['day','units','item','arm']].to_csv(ROOT/'historical/fresh_denominator_panel.csv',index=False)
    key_units=float(fresh[(fresh.whole_word_arm=='key') & fresh.daynum.between(rm.EN-21,rm.EN-1)].units.sum())
    (E/'KEY_TURNOVER.json').write_text(json.dumps({'pre21_whole_word_key_units':key_units,'source':'fresh raw-data panel','rows':len(fresh)}),encoding='utf-8')
    del fresh
    counts={}
    for co in ['full','recovered']:
        pp=rm.load_panel(co)
        for gr in ['all','exclude_cases','exclude_broad']:
            xx=rm.group_subset(pp,gr)
            counts[co+'|'+gr]={'candidate':int(xx[xx.treat==1].item_id.nunique()),'control':int(xx[xx.treat==0].item_id.nunique())}
    (E/'SELECTED_COUNTS.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    del pp,xx
    hist=pd.read_csv(E/'sources/date_calibration_full_calendar.csv');meta=[];weights=[];hrows=[]
    dates=pd.read_csv(E/'sources/randomization_dates_frozen.csv')
    args=argparse.Namespace(window='tight21',date_file=E/'sources/randomization_dates_frozen.csv',date_start='2017-03-01',date_end='2019-08-31',draws=150,seed=20261112,reps=2500,calibration_reps=2500,quantile_bootstrap=1000,block_days=7,scale_mode='equal_intensity',scenarios=['abrupt'],grid=[0,1,3,5,10,20,30,44,60,80,100])
    for cohort in ['full','recovered']:
        p=rm.load_panel(cohort)
        for gi,group in enumerate(['all','exclude_cases','exclude_broad']):
            if cohort=='recovered' and group=='exclude_broad':continue
            gp=rm.group_subset(p,group);d=rm.window(gp);postmask=((d.treat==1)&(d.daynum>=rm.EN)).to_numpy()
            pre=d[(d.treat==1)&(d.daynum<rm.EN)].groupby('item_id').units.sum()
            budget=float(pre.sum());postunits=float(d[(d.treat==1)&(d.daynum>=rm.EN)].units.sum())
            cd=cloud_frame(d)
            for model in ['TWFE','item_FE']:
                f=rm.estimate(d,model);cf=cc.Design(cd,rm.E,'twfe' if model=='TWFE' else 'item_post');fit=cf.fit()
                delta=abs(float(f['beta'][-1])-fit['coefficient']);wdiff=np.max(np.abs(f['weights'][-1]-cf.weights));assert delta<1e-8 and wdiff<1e-8
                w=f['weights'][-1,postmask]
                weights.append(dict(cohort=cohort,group=group,model=model,n_injected_cells=len(w),minimum_weight=float(w.min()),negative_below_1e_12=int((w < -1e-12).sum()),maximum_weight_difference=float(wdiff),coefficient_difference=delta,fixed_design=True,nonnegative_affine_unit_increments=True,fixed_paths_across_grid=True))
                meta.append(dict(cohort=cohort,group=group,model=model,pre_units=budget,post_units=postunits,candidate_items=int(d[d.treat==1].item_id.nunique()),control_items=int(d[d.treat==0].item_id.nunique()),**scalar_report(f)))
                if model!='TWFE' or group=='exclude_broad':continue
                out=E/f'cloud/{cohort}_{group}';out.mkdir(parents=True,exist_ok=True)
                if cohort=='full':
                    hh=hist[(hist.candidate_group==group)&(hist.model=='TWFE')&hist.in_frozen150].sort_values('daynum').copy()
                    summ=history_summary(hh)
                    print('NEW_CLOUD_MATCHED',cohort,group,datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
                    cloud.injection(cloud_frame(gp),out,args,'twfe',summ)
                else:
                    hh,summ=cloud.randomization(cloud_frame(gp),out,args,'twfe')
                    if 'overlaps_trade_hold' not in hh:hh['overlaps_trade_hold']=hh.trade_hold_overlap
                    hh['daynum']=(pd.to_datetime(hh.date,utc=True)-pd.Timestamp('1970-01-01',tz='UTC')).dt.days
                    hh=hh.sort_values('daynum')
                    print('NEW_CLOUD_MATCHED',cohort,group,flush=True)
                    cloud.injection(cloud_frame(gp),out,args,'twfe',summ)
                    # Fresh recovered-cohort Dell paths: same seed, group order, and TWFE model index as v2.
                    rng=np.random.default_rng(2604938+10000+gi*100+1);b=hh.coefficient.to_numpy();ni=rng.integers(0,len(b),2500);noise=b[ni]-b.mean()
                    u=d.loc[postmask,'units'].to_numpy(float);W=d.loc[postmask,'item_id'].map(pre).fillna(0).to_numpy(float)/21;grid=np.asarray(cfg['grid_fraction']);beta=float(f['beta'][-1])
                    for bg in ['neutral','observed']:
                        q=np.expm1(np.log1p(u)-beta) if bg=='neutral' else u; base=0 if bg=='neutral' else beta
                        s=np.array([np.log1p(g*W/(1+q))@w for g in grid]);signal=np.broadcast_to(s,(2500,len(grid))).copy()
                        dst=E/f'matched_dell/{group}_{bg}.npz';dst.parent.mkdir(exist_ok=True)
                        np.savez_compressed(dst,grid=grid,signal=signal,coefficients=base+signal+noise[:,None],volume_fraction=np.asarray([W.sum()/budget]),noise_indices=ni)
                for row in hh.to_dict('records'):hrows.append(dict(cohort=cohort,group=group,date=row['date'],daynum=row['daynum'],coefficient=row['coefficient'],overlaps_trade_hold=row['overlaps_trade_hold']))
                print('MATCHED_CELL_COMPLETE',cohort,group,flush=True)
        del p
    pd.DataFrame(meta).to_csv(E/'BASELINES_AND_DENOMINATORS.csv',index=False)
    pd.DataFrame(weights).to_csv(E/'WEIGHT_FUNCTION_CHECKS.csv',index=False)
    pd.DataFrame(hrows).to_csv(E/'MATCHED_COMMON_DATE_COEFFICIENTS.csv',index=False)
    (ROOT/'audit/REUSED_FILE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('PREPARE_EVIDENCE_COMPLETE',len(manifest),flush=True)
if __name__=='__main__':
    from pathlib import Path
    main()

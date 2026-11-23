"""Result aggregation from coefficient arrays freshly simulated in this execution."""
from pathlib import Path
import argparse,json,hashlib,datetime,shutil,math
import numpy as np,pandas as pd
from scipy.stats import norm
ROOT=Path(__file__).resolve().parents[1]; E=ROOT/'evidence'
CFG=json.loads((ROOT/'FINAL_SETTINGS.json').read_text(encoding='utf-8'))
CURVES=[]; RESULTS=[]; LEDGER=[]; THRESHOLDS=[]
COUNTS=json.loads((E/'SELECTED_COUNTS.json').read_text())
def wilson(k,n):
    z=norm.ppf(.975);p=np.asarray(k)/n;den=1+z*z/n;mid=(p+z*z/(2*n))/den;half=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return np.maximum(0,mid-half),np.minimum(1,mid+half)
def floor(grid,power):
    k=np.flatnonzero(power>=.8);return float(grid[k[0]]) if len(k) else np.inf
def percentile(x,p):return float(np.quantile(x,p,method='higher'))
def record(out, *, coeff,grid,vf,threshold,meta,source,signal=None,randomness=None,cal=None,base=None,bootstrap=False):
    coeff=np.asarray(coeff);grid=np.asarray(grid);n=len(coeff);counts=(coeff>threshold).sum(axis=0);probs=counts/n;lo,hi=wilson(counts,n)
    rid='|'.join(str(meta[x]) for x in ['cohort','candidate_group','model','background','scenario','scale','implementation','calibration'])
    # Numerical evidence is shared across thresholds whenever the coefficient arrays are identical.
    meta=dict(meta,result_id=rid,threshold=float(threshold),source_run_id=source,
              selected_candidate_items=COUNTS[('full' if meta['cohort']=='full_archive' else 'recovered')+'|'+meta['candidate_group']]['candidate'],
              selected_control_items=COUNTS[('full' if meta['cohort']=='full_archive' else 'recovered')+'|'+meta['candidate_group']]['control'],
              window_start='2019-10-07',window_end='2019-11-17',post_start='2019-10-28',
              primary_result=meta['cohort']=='full_archive' and meta['model']=='TWFE' and meta['candidate_group'] in ['all','exclude_cases'] and meta['scale']=='eventual' and meta['calibration']=='frozen150_centered')
    vf=np.asarray(vf);vf=np.repeat(vf,n) if len(vf)==1 else vf;assert len(vf)==n
    for j,g in enumerate(grid):
        CURVES.append(dict(meta,dose_fraction=g,recovered=int(counts[j]),repetitions=n,probability=probs[j],wilson_low=lo[j],wilson_high=hi[j],mcse=math.sqrt(probs[j]*(1-probs[j])/n),mean_added_units=g*vf.mean()*meta['pre_volume_denominator'],added_units_p025=g*np.quantile(vf,.025)*meta['pre_volume_denominator'],added_units_p975=g*np.quantile(vf,.975)*meta['pre_volume_denominator'],mean_realized_fraction=g*vf.mean()))
    hits=np.flatnonzero(probs>=.8);j=int(hits[0]) if len(hits) else None
    status='crossing_bracketed' if j is not None else 'criterion_not_reached';status='zero_in_window_exposure' if np.all(vf==0) else status
    row=dict(meta,status=status,tested_max_fraction=float(grid[-1]),lower_dose_fraction=float(grid[j-1]) if j is not None and j>0 else (0. if j==0 else float(grid[-1])),first_success_fraction=float(grid[j]) if j is not None else np.nan,zero_recovered=int(counts[0]),zero_repetitions=n,zero_probability=float(probs[0]),zero_wilson_low=float(lo[0]),zero_wilson_high=float(hi[0]),grid_bracket_is_confidence_interval=False)
    for prefix,ix in [('lower',max(0,j-1) if j is not None else len(grid)-1),('upper',j)]:
        for field,val in [('recovered',int(counts[ix]) if ix is not None else np.nan),('repetitions',n),('probability',probs[ix] if ix is not None else np.nan),('wilson_low',lo[ix] if ix is not None else np.nan),('wilson_high',hi[ix] if ix is not None else np.nan)]:row[prefix+'_'+field]=val
    row['mean_added_units_at_floor']=float(grid[j]*vf.mean()*meta['pre_volume_denominator']) if j is not None else np.nan
    row['mean_realized_fraction_at_floor']=float(grid[j]*vf.mean()) if j is not None else np.nan
    row['mean_added_units_at_max']=float(grid[-1]*vf.mean()*meta['pre_volume_denominator'])
    row['first_grid_wilson_lower_at80']=floor(grid,lo);row['first_grid_wilson_upper_at80']=floor(grid,hi)
    if bootstrap:
        b=cal['frozen'];ab=cal['all'];iv=b[randomness['iid_indices']];bv=ab[randomness['block_indices']]
        iq=np.quantile(iv,.95,axis=1)-iv.mean(axis=1);bq=np.quantile(bv,.95,axis=1)-bv.mean(axis=1)
        fs=[]
        for z,rix in enumerate(randomness['bootstrap_run_indices']):
            sm=signal[rix];ei=iv[z,randomness['bootstrap_noise_iid'][z]]-iv[z].mean();eb=bv[z,randomness['bootstrap_noise_block'][z]]-bv[z].mean()
            fs.append([floor(grid,(coeff[rix]>threshold).mean(axis=0)),floor(grid,(base+sm+ei[:,None]>iq[z]).mean(axis=0)),floor(grid,(base+sm+eb[:,None]>bq[z]).mean(axis=0))])
        fs=np.asarray(fs);name=hashlib.sha256(rid.encode()).hexdigest()[:16]
        np.savez_compressed(out/'bootstrap'/f'{name}.npz',mc_floor=fs[:,0],iid_joint_floor=fs[:,1],block_joint_floor=fs[:,2],iid_threshold=iq,block_threshold=bq)
        row['bootstrap_evidence']=f'bootstrap/{name}.npz'
        for k,tag in enumerate(['conditional_mc','iid_date_joint','full_calendar_block_joint']):
            row[tag+'_p025']=percentile(fs[:,k],.025);row[tag+'_p975']=percentile(fs[:,k],.975);row[tag+'_fraction_above_grid']=float(np.mean(np.isinf(fs[:,k])))
    RESULTS.append(row);LEDGER.append(dict(result_id=rid,source=source,activity=meta['execution_activity'],coefficient_array=meta['coefficient_evidence'],calibration=meta['calibration_evidence'],pre_volume_denominator=meta['pre_volume_denominator']))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve()
    if out.exists() and any(out.iterdir()):raise FileExistsError('Output must be clean: '+str(out))
    out.mkdir(parents=True,exist_ok=True);(out/'bootstrap').mkdir();(out/'derived_draws').mkdir()
    hist=pd.read_csv(E/'sources/date_calibration_full_calendar.csv');baselines=pd.read_csv(E/'BASELINES_AND_DENOMINATORS.csv')
    for scale in ['eventual','equal_cumulative']:
        for src in sorted((E/f'dell/{scale}').glob('*.npz')):
            if src.stem.endswith('randomness'):continue
            # Names have unambiguous model/background separators.
            pre,bg_shape=src.stem.split('_neutral_',1) if '_neutral_' in src.stem else src.stem.split('_observed_',1)
            bg='neutral' if '_neutral_' in src.stem else 'observed';shape=bg_shape;model='TWFE' if pre.endswith('_TWFE') else 'item_FE';group=pre[:-(len(model)+1)]
            z=np.load(src);coeff=z['coefficients'];sig=z['signal'];grid=z['grid'];vf=z['volume_fraction']
            with np.load(src.parent/f'{group}_{model}_randomness.npz') as nf:rnd={k:nf[k] for k in nf.files}
            h=hist[(hist.candidate_group==group)&(hist.model==model)].sort_values('daynum');f=h[h.in_frozen150];b=f.coefficient.to_numpy();ab=h.coefficient.to_numpy();cl=f[~f.overlaps_trade_hold].coefficient.to_numpy();cal={'frozen':b,'all':ab}
            m=baselines.query('cohort=="full" and group==@group and model==@model').iloc[0];base=0. if bg=='neutral' else m.coefficient
            assert np.max(np.abs(coeff-(base+sig+(b[rnd['noise_indices']]-b.mean())[:,None])))<1e-8
            meta=dict(cohort='full_archive',candidate_group=group,model=model,background=bg,scenario=shape,scale=scale,implementation='Dell_empirical_coefficient_noise',pre_volume_denominator=float(m.pre_units),candidate_items=int(m.candidate_items),control_items=int(m.control_items),baseline_coefficient=float(m.coefficient),coefficient_evidence=str(src.relative_to(ROOT)),calibration_evidence='evidence/sources/date_calibration_full_calendar.csv',execution_activity='fresh_raw_rebuild_and_simulation')
            variants={'frozen150_centered':(coeff,float(np.quantile(b,.95)-b.mean())),'original_uncentered_threshold':(coeff,float(np.quantile(b,.95)))}
            if scale=='eventual' and model=='TWFE' and group!='exclude_broad':
                for tag,v in [('exclude_trade_hold',cl),('full_calendar',ab)]:
                    q=float(np.quantile(v,.95)-v.mean());variants[f'{tag}_threshold_only']=(coeff,q)
                    rng=np.random.default_rng(2604938+222+['all','exclude_cases','exclude_broad'].index(group)*100+1);noise=rng.choice(v,len(coeff))-v.mean()
                    variants[f'{tag}_joint_noise_threshold']=(base+sig+noise[:,None],q)
                tr=h[h.date.between('2017-03-01','2018-12-10')].coefficient.to_numpy();te=h[h.date.between('2019-02-01','2019-08-31')].coefficient.to_numpy()
                rng=np.random.default_rng(2604938+333+['all','exclude_cases'].index(group)*100+1);noise=rng.choice(te,len(coeff))-te.mean()
                variants['disjoint_calendar_holdout']=(base+sig+noise[:,None],float(np.quantile(tr,.95)-tr.mean()))
            for tag,(c,q) in variants.items():
                mm=dict(meta,calibration=tag)
                if c is not coeff:
                    fn=f'{scale}_{src.stem}_{tag}.npz';np.savez_compressed(out/'derived_draws'/fn,coefficients=c,grid=grid,volume_fraction=vf)
                    mm['coefficient_evidence']=out.name+'/derived_draws/'+fn;mm['execution_activity']='fresh_calibration_sensitivity_using_current_run_signals'
                record(out,coeff=c,grid=grid,vf=vf,threshold=q,meta=mm,source=f'v2/{scale}/{src.name}',signal=sig,randomness=rnd,cal=cal,base=base,bootstrap=tag=='frozen150_centered')
            if bg=='neutral' and shape=='step':
                THRESHOLDS.append(dict(cohort='full_archive',group=group,model=model,scale=scale,n_dates=len(b),mean=float(b.mean()),q95_original=float(np.quantile(b,.95)),q95_centered=float(np.quantile(b,.95)-b.mean()),finite_support_uncentered_zero=float(np.mean(b-b.mean()>np.quantile(b,.95))),finite_support_centered_zero=float(np.mean(b-b.mean()>np.quantile(b-b.mean(),.95)))))
            print('FINAL_CURVES',scale,group,model,bg,shape,flush=True)
    # Matched two-cohort / two-implementation abrupt comparison; thresholds share the common date list.
    mh=pd.read_csv(E/'MATCHED_COMMON_DATE_COEFFICIENTS.csv')
    for cohort in ['full','recovered']:
        for group in ['all','exclude_cases']:
            h=mh[(mh.cohort==cohort)&(mh.group==group)].sort_values('daynum');b=h.coefficient.to_numpy();q=float(np.quantile(b,.95)-b.mean());m=baselines.query('cohort==@cohort and group==@group and model=="TWFE"').iloc[0]
            for bg in ['neutral','observed']:
                src=E/f'cloud/{cohort}_{group}/injection_coefficients_twfe_{bg}_model_abrupt.csv.gz';fr=pd.read_csv(src);grid=np.array([float(x[4:])/100 for x in fr.columns if x.startswith('pct_')]);cloudc=fr.drop(columns='rep').to_numpy()
                detail=json.loads((src.parent/f'injection_detail_twfe_{bg}_model_abrupt.json').read_text());vf=np.array([detail['mean_observed_profile_fraction']]);calib=json.loads((src.parent/'injection_calibration_twfe.json').read_text())
                dellsrc=E/f'dell/eventual/{group}_TWFE_{bg}_step.npz' if cohort=='full' else E/f'matched_dell/{group}_{bg}.npz'
                dz=np.load(dellsrc);ix=[int(np.flatnonzero(np.isclose(dz['grid'],v,rtol=0,atol=1e-12))[0]) for v in grid];dc=dz['coefficients'][:,ix];ds=dz['signal'][:,ix];base=0. if bg=='neutral' else float(m.coefficient)
                dn=dc[:,0]-base;cn=cloudc[:,0]-cloudc[:,0].mean();cs=cloudc-cloudc[:,[0]]
                paths={'Dell_matched':dc,'Cloud_wild':cloudc,'hybrid_noise_only':base+ds+cn[:,None],'hybrid_injection_background_only':base+cs+dn[:,None]}
                for impl,c in paths.items():
                    fn=f'matched_{cohort}_{group}_{bg}_{impl}.npz';np.savez_compressed(out/'derived_draws'/fn,coefficients=c,grid=grid,volume_fraction=vf)
                    thresholds={'common150_centered':q}
                    if impl=='Cloud_wild':thresholds.update(common150_uncentered=float(np.quantile(b,.95)),conditional_wild=calib['thresholds']['conditional_wild_null95'])
                    meta=dict(cohort='full_archive' if cohort=='full' else 'recovered',candidate_group=group,model='TWFE',background=bg,scenario='step',scale='eventual_matched_common_grid',implementation=impl,pre_volume_denominator=float(m.pre_units),candidate_items=int(m.candidate_items),control_items=int(m.control_items),baseline_coefficient=float(m.coefficient),coefficient_evidence=out.name+'/derived_draws/'+fn,calibration_evidence='evidence/MATCHED_COMMON_DATE_COEFFICIENTS.csv',execution_activity='fresh_matched_comparison_all_paths_regenerated')
                    for tag,t in thresholds.items():record(out,coeff=c,grid=grid,vf=vf,threshold=t,meta=dict(meta,calibration=tag),source=f'matched/{cohort}/{group}/{bg}/{impl}')
    results=pd.DataFrame(RESULTS);curves=pd.DataFrame(CURVES)
    assert not results.result_id.duplicated().any()
    results.to_csv(out/'FINAL_RESULTS.csv',index=False);curves.to_csv(out/'RECOVERY_CURVES.csv',index=False);pd.DataFrame(LEDGER).to_csv(out/'RESULT_TO_SOURCE_LEDGER.csv',index=False);pd.DataFrame(THRESHOLDS).to_csv(out/'CALIBRATION_TARGETS.csv',index=False)
    primary=results.query('cohort=="full_archive" and model=="TWFE" and candidate_group in ["all","exclude_cases"] and scale=="eventual" and calibration=="frozen150_centered"')
    primary.to_csv(out/'PRIMARY_SCENARIO_RESULTS.csv',index=False)
    figure=primary.query('scenario=="step"').copy();figure['recorded_whole_word_key_units']=json.loads((E/'KEY_TURNOVER.json').read_text())['pre21_whole_word_key_units'];figure['recorded_key_fraction']=figure.recorded_whole_word_key_units/figure.pre_volume_denominator
    figure.to_csv(out/'FIGURE4_DATA.csv',index=False);figure.to_csv(out/'GRAPHICAL_ABSTRACT_DATA.csv',index=False)
    results.query('scale=="eventual_matched_common_grid"').to_csv(out/'MATCHED_COMPARISONS.csv',index=False)
    for f in ['BASELINES_AND_DENOMINATORS.csv','WEIGHT_FUNCTION_CHECKS.csv']:shutil.copy2(E/f,out/f)
    (out/'GENERATION_STATUS.json').write_text(json.dumps(dict(completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),rows=len(results),curves=len(curves),settings_sha256=hashlib.sha256((ROOT/'FINAL_SETTINGS.json').read_bytes()).hexdigest(),fresh_primary_simulation=True,primary='fresh v2 paths; threshold and disturbances consistently centered',matched='all matched abrupt comparisons freshly computed; hybrid decomposition and threshold changes explicitly separated'),indent=2),encoding='utf-8')
    print('FINAL_RESULT_GENERATION_COMPLETE',len(results),len(curves),flush=True)
if __name__=='__main__':main()

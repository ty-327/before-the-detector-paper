"""POST-EXECUTION comparison only: never imported by a fitting/simulation stage."""
from pathlib import Path
import argparse,json,math
import numpy as np,pandas as pd
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',type=Path,required=True);ap.add_argument('--reference',type=Path,required=True);a=ap.parse_args()
    run=a.run.resolve();ref=a.reference.resolve();out=run/'comparison';out.mkdir(exist_ok=True)
    specs={'FINAL_RESULTS.csv':['result_id'],'RECOVERY_CURVES.csv':['result_id','dose_fraction'],'PRIMARY_SCENARIO_RESULTS.csv':['result_id'],'EQUAL_CUMULATIVE_RESULTS.csv':['result_id'],'MATCHED_COMPARISONS.csv':['result_id'],'CALIBRATION_TARGETS.csv':['cohort','group','model','scale'],'BASELINES_AND_DENOMINATORS.csv':['cohort','group','model'],'EMPIRICAL_RESPONSE_SPECIFICATIONS.csv':['candidate_group','shape'],'MATCHED_AGGREGATE_VOLUMES.csv':['group']}
    ignored={'coefficient_evidence','calibration_evidence','execution_activity','source_run_id','bootstrap_evidence'}
    records=[];diffs=[]
    for filename,keys in specs.items():
        expected=pd.read_csv(ref/'supplementary/tables'/filename);actual=pd.read_csv(run/'results'/filename)
        assert not expected.duplicated(keys).any() and not actual.duplicated(keys).any()
        e=expected.set_index(keys);g=actual.set_index(keys);missing=e.index.difference(g.index);extra=g.index.difference(e.index)
        records.append(dict(table=filename,field='ROW_KEYS',checked=len(e),different=len(missing)+len(extra),max_absolute_difference=0))
        common=e.index.intersection(g.index);e=e.loc[common];g=g.loc[common]
        for col in expected.columns:
            if col in keys or col in ignored:continue
            if col not in g:
                records.append(dict(table=filename,field=col,checked=len(e),different=len(e),max_absolute_difference=np.nan));continue
            if pd.api.types.is_numeric_dtype(e[col]) and not pd.api.types.is_bool_dtype(e[col]):
                x=e[col].to_numpy(float);y=g[col].to_numpy(float)
                exact=any(t in col for t in ['recovered','repetitions','items']) or col in ['n','rank','dates','n_dates','pre_units','post_units','pre_volume_denominator','first_success_fraction','lower_dose_fraction'] or col.endswith(('_p025','_p975')) and 'units' not in col
                tol=0 if exact else (1e-5 if 'units' in col else 1e-8)
                ok=np.isclose(x,y,atol=tol,rtol=1e-10 if 'units' in col and not exact else 0,equal_nan=True)
                dd=np.abs(x-y);finite=dd[np.isfinite(dd)];maxdiff=float(finite.max()) if len(finite) else 0.
            else:
                x=e[col].fillna('<NA>').astype(str).to_numpy();y=g[col].fillna('<NA>').astype(str).to_numpy();ok=x==y;maxdiff=np.nan
            records.append(dict(table=filename,field=col,checked=len(e),different=int((~ok).sum()),max_absolute_difference=maxdiff))
            for i in np.flatnonzero(~ok):diffs.append(dict(table=filename,key=str(common[i]),field=col,expected=str(x[i]),actual=str(y[i])))
    # Figure data are separately checked against the numerical v48 figure source.
    expected=pd.read_csv(ref/'supplementary/figures/FIGURE4_DATA.csv').set_index('result_id');actual=pd.read_csv(run/'results/FIGURE4_DATA.csv').set_index('result_id')
    for col in ['first_success_fraction','recorded_whole_word_key_units','recorded_key_fraction','pre_volume_denominator']:
        x=expected[col];y=actual.loc[x.index,col];ok=np.isclose(x,y,atol=1e-10,rtol=0,equal_nan=True)
        records.append(dict(table='FIGURE4_DATA.csv',field=col,checked=len(x),different=int((~ok).sum()),max_absolute_difference=float(np.max(np.abs(x-y)))))
    pd.DataFrame(records).to_csv(out/'V48_TABLE_COMPARISON.csv',index=False)
    pd.DataFrame(diffs,columns=['table','key','field','expected','actual']).to_csv(out/'V48_NUMERICAL_DISCREPANCIES.csv',index=False)
    status={'status':'MATCH' if sum(r['different'] for r in records)==0 else 'DIFFERENCES_REPORTED','table_count':len(specs)+1,'field_checks':len(records),'differing_cells_or_keys':sum(r['different'] for r in records),'reference':str(ref),'scope':'Main simulation and supplementary tables plus Figure4 data. Manuscript prose and legacy descriptives assessed separately. No estimation settings changed by this check.'}
    (out/'COMPARISON_STATUS.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
if __name__=='__main__':main()

"""Separate arithmetic checker. Does not import the generating or estimator code."""
from pathlib import Path
import csv,json,math,statistics,hashlib,re,argparse,io
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release_final'; checks=[]
INDEX_RECIPE_SHA256='319da603a93674b5d3b05568958726a4ab03e3bc3782019be8db23cbddaeb9ac'

def verify_current_evidence():
    """Check current files; an earlier restoration receipt is never sufficient."""
    recipe_path=ROOT/'reviewer_tools/REPLAY_INDEX_RECIPE.json'
    frozen={}
    if recipe_path.is_file():
        if hashlib.sha256(recipe_path.read_bytes()).hexdigest()!=INDEX_RECIPE_SHA256:
            raise ValueError('Frozen index recipe SHA-256 mismatch')
        recipe=json.loads(recipe_path.read_text(encoding='utf-8'))
        frozen={entry['path']:entry for entry in recipe['files']}
        if recipe['schema_version']!=1 or len(frozen)!=7 or sum(len(e['arrays']) for e in frozen.values())!=42:
            raise ValueError('Frozen index recipe must declare exactly seven files and 42 arrays')
    elif (ROOT/'INDEX_RESTORE_STATUS.json').exists():
        raise FileNotFoundError('The compact replay requires its frozen index recipe')
    manifest=json.loads((ROOT/'audit/REUSED_FILE_MANIFEST.json').read_text(encoding='utf-8'))
    paths=[entry['evidence'].replace('\\','/') for entry in manifest]
    if len(set(paths))!=len(paths) or not set(frozen).issubset(paths):
        raise ValueError('Evidence manifest has duplicate paths or omits a frozen index file')
    verified=[]
    for entry,relative in zip(manifest,paths):
        path=(ROOT/relative).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Evidence path escapes the workspace: '+relative)
        current_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        original_bytes_match=current_hash==entry['sha256']
        if relative in frozen:
            declared=frozen[relative]
            if entry['sha256']!=declared['original_sha256']:
                raise ValueError('Original index hash differs from the frozen recipe: '+relative)
            with np.load(path,allow_pickle=False) as archive:
                if archive.files!=[spec['name'] for spec in declared['arrays']]:
                    raise ValueError('Current frozen-array names/order differ: '+relative)
                for spec in declared['arrays']:
                    array=archive[spec['name']]
                    observed=(list(array.shape),array.dtype.str,hashlib.sha256(array.tobytes(order='C')).hexdigest())
                    expected=(spec['shape'],spec['dtype'],spec['sha256_c_order_bytes'])
                    if observed!=expected:
                        raise ValueError('Current frozen-array verification failed: '+relative+':'+spec['name'])
        elif not original_bytes_match:
            raise ValueError('Current evidence SHA-256 mismatch: '+relative)
        verified.append({'path':relative,'sha256':current_hash,'original_container_match':original_bytes_match,
                         'arrays_verified':len(frozen[relative]['arrays']) if relative in frozen else 0})
    return {'status':'PASS','scope':'Current evidence files only; no raw-data processing or model fitting',
            'files_verified':len(verified),'frozen_index_files_verified':len(frozen),
            'arrays_verified':sum(v['arrays_verified'] for v in verified),
            'strict_hash_files_verified':len(verified)-len(frozen),'prior_restore_receipt_trusted':False,
            'recipe_sha256':INDEX_RECIPE_SHA256 if frozen else None,'files':verified}

def rows(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def ck(label,ok):
    checks.append({'check':label,'passed':bool(ok)})
    if not ok:raise AssertionError(label)
def close(a,b,t=1e-10):
    a,b=float(a) if a!='' else math.nan,float(b) if b!='' else math.nan
    return (math.isnan(a) and math.isnan(b)) or a==b or abs(a-b)<=t
def q7(a,p):
    v=sorted(a);pos=(len(v)-1)*p;i=math.floor(pos);r=pos-i;return v[i]*(1-r)+v[min(i+1,len(v)-1)]*r
def wi(k,n):
    p=k/n;z=statistics.NormalDist().inv_cdf(.975);d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return max(0,c-h),min(1,c+h)
def crossing(g,c):
    good=np.where(c>=.8)[0];return float(g[good[0]]) if len(good) else math.inf
def main():
    global OUT
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=OUT);ap.add_argument('--allow-missing-panel',action='store_true');ap.add_argument('--verify-evidence-only',action='store_true',help='Verify current evidence files without running result arithmetic');args=ap.parse_args();OUT=args.out.resolve()
    evidence=verify_current_evidence()
    if args.verify_evidence_only:
        print(json.dumps(evidence),flush=True)
        return
    result=rows(OUT/'FINAL_RESULTS.csv');curves=rows(OUT/'RECOVERY_CURVES.csv');bym={}
    for r in curves:bym.setdefault(r['result_id'],[]).append(r)
    ck('unique result ids',len(set(r['result_id'] for r in result))==len(result))
    h=rows(ROOT/'evidence/sources/date_calibration_full_calendar.csv');mh=rows(ROOT/'evidence/MATCHED_COMMON_DATE_COEFFICIENTS.csv')
    baseline=rows(ROOT/'evidence/BASELINES_AND_DENOMINATORS.csv');ncache={}
    for r in result:
        rid=r['result_id'];src=ROOT/Path(r['coefficient_evidence'].replace('\\','/'))
        if str(src) not in ncache:
            with np.load(src) as z:ncache[str(src)]={k:z[k] for k in z.files if k in ['coefficients','grid','volume_fraction','signal']}
        z=ncache[str(src)];coeff=z['coefficients'];g=z['grid'];n=len(coeff);q=float(r['threshold']);k=np.sum(coeff>q,axis=0)
        cs=sorted(bym[rid],key=lambda x:float(x['dose_fraction']));ck(rid+' rows',len(cs)==len(g))
        for j,c in enumerate(cs):
            low,high=wi(int(k[j]),n)
            ck(rid+f' dose {g[j]} count/probability/interval/units',int(c['recovered'])==k[j] and int(c['repetitions'])==n and close(c['probability'],k[j]/n) and close(c['wilson_low'],low) and close(c['wilson_high'],high) and close(c['dose_fraction'],g[j]) and close(c['mean_added_units'],g[j]*float(np.mean(z['volume_fraction']))*float(r['pre_volume_denominator']),1e-5))
        hit=np.flatnonzero(k/n>=.8);j=int(hit[0]) if len(hit) else None;floor=float(g[j]) if j is not None else math.nan;lower=float(g[max(j-1,0)]) if j is not None else float(g[-1])
        ck(rid+' first qualifying grid',close(r['first_success_fraction'],floor) and close(r['lower_dose_fraction'],lower))
        ck(rid+' endpoints',int(float(r['lower_recovered']))==int(k[max(j-1,0)] if j is not None else k[-1]) and int(r['zero_recovered'])==int(k[0]) and (j is None or int(float(r['upper_recovered']))==int(k[j])))
        cohort='full' if r['cohort']=='full_archive' else 'recovered';group=r['candidate_group'];model=r['model']
        m=next(x for x in baseline if x['cohort']==cohort and x['group']==group and x['model']==model)
        ck(rid+' denominator cohort',close(r['pre_volume_denominator'],m['pre_units'],0))
        tag=r['calibration']
        if r['scale']!='eventual_matched_common_grid':
            a=sorted([x for x in h if x['candidate_group']==group and x['model']==model],key=lambda x:int(x['daynum']));fr=[x for x in a if x['in_frozen150']=='True'];vals=[float(x['coefficient']) for x in fr]
            if tag.startswith('exclude_trade_hold'):vals=[float(x['coefficient']) for x in fr if x['overlaps_trade_hold']=='False']
            if tag.startswith('full_calendar'):vals=[float(x['coefficient']) for x in a]
            if tag=='disjoint_calendar_holdout':vals=[float(x['coefficient']) for x in a if '2017-03-01'<=x['date']<='2018-12-10']
            expected=q7(vals,.95)-(0 if tag=='original_uncentered_threshold' else statistics.mean(vals));ck(rid+' independently centred quantile',abs(q-expected)<1e-11)
        elif tag.startswith('common150'):
            vals=[float(x['coefficient']) for x in mh if x['cohort']==cohort and x['group']==group];expected=q7(vals,.95)-(statistics.mean(vals) if tag.endswith('centered') and not tag.endswith('uncentered') else 0)
            ck(rid+' matched quantile',abs(q-expected)<1e-11)
        else:
            cr=rows(ROOT/f'evidence/cloud/{cohort}_{group}/injection_null_calibration_twfe.csv');ck(rid+' conditional null quantile',abs(q-q7([float(x['coefficient']) for x in cr],.95))<1e-11)
        if r.get('bootstrap_evidence'):
            with np.load(OUT/Path(r['bootstrap_evidence'].replace('\\','/'))) as bf:bs={k:bf[k] for k in bf.files}
            rndpath=src.parent/f'{group}_{model}_randomness.npz'
            with np.load(rndpath) as bz:rnd={k:bz[k] for k in bz.files}
            aa=sorted([x for x in h if x['candidate_group']==group and x['model']==model],key=lambda x:int(x['daynum']));allb=np.array([float(x['coefficient']) for x in aa]);fb=np.array([float(x['coefficient']) for x in aa if x['in_frozen150']=='True']);base=0 if r['background']=='neutral' else float(m['coefficient'])
            for j,idx in enumerate(rnd['bootstrap_run_indices']):
                mc=crossing(g,np.sum(coeff[idx]>q,axis=0)/n);iv=fb[rnd['iid_indices'][j]];bv=allb[rnd['block_indices'][j]]
                iq=q7(iv,.95)-statistics.mean(iv);bq=q7(bv,.95)-statistics.mean(bv)
                ei=iv[rnd['bootstrap_noise_iid'][j]]-statistics.mean(iv);eb=bv[rnd['bootstrap_noise_block'][j]]-statistics.mean(bv)
                iid=crossing(g,np.sum(base+z['signal'][idx]+ei[:,None]>iq,axis=0)/n);block=crossing(g,np.sum(base+z['signal'][idx]+eb[:,None]>bq,axis=0)/n)
                ck(rid+f' bootstrap {j}',close(mc,bs['mc_floor'][j]) and close(iid,bs['iid_joint_floor'][j]) and close(block,bs['block_joint_floor'][j]))
            for tag,key in [('conditional_mc','mc_floor'),('iid_date_joint','iid_joint_floor'),('full_calendar_block_joint','block_joint_floor')]:
                v=sorted(bs[key]);ck(rid+' bootstrap quantiles '+tag,close(r[tag+'_p025'],v[math.ceil((len(v)-1)*.025)]) and close(r[tag+'_p975'],v[math.ceil((len(v)-1)*.975)]))
    # Independently sum candidate and key denominators from freshly rebuilt CSV; no data transformations from generating code.
    src=ROOT/'historical/fresh_denominator_panel.csv'
    defs=rows(ROOT/'evidence/sources/container_definitions.csv');cases={x['item'] for x in defs if x['key_dependent_case']=='True'};broad={x['item'] for x in defs if x['all_named_containers']=='True'}
    sums={x:{'pre':0,'post':0} for x in ['all','exclude_cases','exclude_broad','whole_word_keys']};selected=set();keynames=set()
    if not src.exists() and not args.allow_missing_panel:raise FileNotFoundError('Local denominator verification requires '+str(src)+'; use --allow-missing-panel only to check packaged coefficients without rescanning raw observations.')
    if not src.exists():
        sums=json.loads((ROOT/'evidence/INDEPENDENT_DENOMINATORS_CHECKED_LOCAL.json').read_text())
    with (src.open(encoding='utf-8-sig',newline='') if src.exists() else io.StringIO('day,units,item,arm\n')) as f:
        for x in csv.DictReader(f):
            item=x['item'];arm=x['arm'];day=x['day'][:10]
            if arm=='substitute':selected.add(item)
            if arm=='key' and re.search(r'\bKey\b',item):keynames.add(item)
            if not '2019-10-07'<=day<='2019-11-17':continue
            period='pre' if day<'2019-10-28' else 'post';v=int(float(x['units']))
            if arm=='substitute':
                sums['all'][period]+=v
                if item not in cases:sums['exclude_cases'][period]+=v
                if item not in broad:sums['exclude_broad'][period]+=v
            if arm=='key' and re.search(r'\bKey\b',item):sums['whole_word_keys'][period]+=v
    if src.exists():ck('selected candidate/case/key counts',len(selected)==597 and len(selected&cases)==29 and len(keynames)==27)
    for r in result:ck(r['result_id']+' agrees with verified CSV denominator',int(float(r['pre_volume_denominator']))==sums[r['candidate_group']]['pre'])
    figs=rows(OUT/'FIGURE4_DATA.csv');mapping={x['result_id']:x for x in result}
    for x in figs:
        ck('figure row '+x['result_id'],all(x[k]==v for k,v in mapping[x['result_id']].items()) and close(x['recorded_key_fraction'],sums['whole_word_keys']['pre']/sums[x['candidate_group']]['pre']))
    # Recheck the current files after the arithmetic. Only the seven pinned index paths
    # may have different NPZ bytes, and their current arrays must match the frozen recipe.
    evidence=verify_current_evidence()
    for entry in evidence['files']:
        ck('fresh current-run evidence hash '+entry['path'],True)
    (OUT/'INDEPENDENT_DENOMINATORS.json').write_text(json.dumps(sums,indent=2),encoding='utf-8')
    status={'status':'PASS','checks':len(checks),'result_rows':len(result),'curve_rows':len(curves),'checker':'separately written arithmetic, quantile, Wilson, floor, bootstrap and CSV-denominator code; same agent, not independent human replication','fresh_csv_rows_scanned':json.loads((ROOT/'evidence/KEY_TURNOVER.json').read_text())['rows'] if src.exists() else 0,'raw_denominator_check_this_execution':src.exists(),'current_evidence_verification':evidence}
    (OUT/'CHECK_STATUS.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
    with open(OUT/'CHECK_LOG.csv','w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=['check','passed']);w.writeheader();w.writerows(checks)
    print(json.dumps(status),flush=True)
if __name__=='__main__':main()

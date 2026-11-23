"""Fresh raw-data execution. Expected results are never read by analytical stages."""
from pathlib import Path
import argparse, hashlib, json, zipfile, subprocess, sys, os, datetime, shutil, platform
SOURCE=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--work-dir',type=Path,required=True)
    ap.add_argument('--stage',choices=['raw','analysis','final','all'],default='all');a=ap.parse_args();root=a.work_dir.resolve()
    if not root.exists():
        root.mkdir(parents=True)
        for rel in ['scripts','inputs','revision','revision_extensions','provenance']:
            shutil.copytree(SOURCE/rel,root/rel)
        for rel in ['FINAL_SETTINGS.json','REPRODUCTION_SPECIFICATION.json','requirements.txt']:
            shutil.copy2(SOURCE/rel,root/rel)
    for rel in ['audit','audit/daily_cache','historical','tables','corrected_analysis','logs','tmp','tmp/matplotlib','figures','verification','reports','revision_extensions/v2/figures']:
        (root/rel).mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',TEMP=str(root/'tmp'),TMP=str(root/'tmp'),MPLCONFIGDIR=str(root/'tmp/matplotlib'))
    commands=[];start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (root/'logs'/f'ENVIRONMENT_{a.stage}.json').write_text(json.dumps({'start_utc':start,'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'argv':sys.argv,'environment_overrides':{k:env[k] for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','TEMP','TMP','MPLCONFIGDIR']}},indent=2),encoding='utf-8')
    def run(name,*args):
        cmd=[sys.executable,str(root/'scripts'/name),*map(str,args)];log=root/'logs'/f'{a.stage}_{len(commands):02}_{name}.log'
        record={'command':cmd,'cwd':str(root),'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'script_sha256':sha(root/'scripts'/name),'log':str(log.relative_to(root))}
        print('START',name,record['start_utc'],flush=True)
        with log.open('w',encoding='utf-8') as out:
            out.write(json.dumps(record)+'\n');out.flush()
            result=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
            record.update(end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=result.returncode)
            out.write('\n'+json.dumps(record)+'\n')
        commands.append(record);(root/'logs'/f'COMMANDS_{a.stage}.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
        print('END',name,'exit',result.returncode,flush=True)
        if result.returncode:raise SystemExit(result.returncode)
    if a.stage in ['raw','all']:
        dest=root/'inputs/download_snapshot'
        if dest.exists():raise FileExistsError('Raw stage requires a clean directory; existing data are not overwritten')
        manifest=json.loads((root/'inputs/public_data_manifest.json').read_text());actual=sha(a.archive)
        if actual!=manifest['archive_sha256']:raise ValueError('ZIP hash mismatch; scientific snapshot cannot be silently substituted')
        dest.mkdir();records=[]
        with zipfile.ZipFile(a.archive) as z:
            for member in z.infolist():
                target=(dest/member.filename).resolve()
                if not target.is_relative_to(dest):raise ValueError('Unsafe ZIP member')
                z.extract(member,dest)
        for entry in manifest['raw_csv_hashes']:
            rel=Path(entry['path'].replace('\\','/'));p=root/rel
            h=sha(p)
            if h!=entry['sha256'] or p.stat().st_size!=entry['bytes']:raise ValueError('Raw member mismatch: '+str(rel))
            records.append({'path':str(rel),'sha256':h,'bytes':p.stat().st_size})
        (root/'inputs/download_manifest.json').write_text(json.dumps({'sha256':actual,'source':str(a.archive.resolve()),'verified_members':len(records),'fresh_extraction':True,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2),encoding='utf-8')
        (root/'audit/RAW_MEMBER_HASHES.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        print('RAW_ARCHIVE_VERIFIED',len(records),flush=True)
        for name in ['audit_raw.py','rebuild_historical_cohort.py','reconcile_panels.py','supplement_data_audit.py']:
            run(name)
    if a.stage in ['analysis','final','all']:
        receipt=json.loads((root/'inputs/download_manifest.json').read_text())
        if not receipt.get('fresh_extraction') or receipt['sha256']!=json.loads((root/'inputs/public_data_manifest.json').read_text())['archive_sha256']:
            raise ValueError('Analysis requires the successful fresh raw-stage receipt for the declared snapshot')
    if a.stage in ['analysis','all']:
        for name in ['computational_checks.py','validate_fe_engine.py','validate_fresh_inputs.py','revision_models.py','date_randomization.py']:
            run(name)
        run('injection_revision.py','--v2');run('injection_revision.py','--v2','--equal-cumulative')
        for name in ['s1b_cache_reconstruction.py','s1b_corrected.py','descriptive_reconstruction.py','finish_data_quality.py','resolve_display_names.py','audit_timestamps.py','timestamp_event_sensitivity.py','linearmodels_crosscheck.py','concentration_reconstruction.py']:
            run(name)
        run('s1b_cache_reconstruction.py','--historical-file-set');run('run_s1b_literal.py')
    if a.stage in ['final','all']:
        run('prepare_evidence.py');run('generate_results.py','--out',root/'results');run('check_results.py','--out',root/'results');run('release_figures.py')
    print('STAGE_COMPLETE',a.stage,datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
if __name__=='__main__':main()

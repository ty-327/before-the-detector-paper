"""Execute original per-file weighted-average and report logic, with isolated outputs."""
from pathlib import Path
import sys,subprocess,json,datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/cloud'))
import run_s1b_adapter
real_run=subprocess.run
def parallel(cmd,**kw):return real_run([sys.executable,'-u',str(ROOT/'scripts/cloud_s1b_parallel_worker.py'),cmd[1]],**kw)
if __name__=='__main__':
    (ROOT/'audit/S1B_CONCURRENCY.json').write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'workers':16,'changes':'Three isolated I/O substitutions plus ordered per-file parallel execution. Original np.average and statistical/report statements retained; source and executed AST saved.','status':'new execution of recovered code, not recovered historical output'},indent=2))
    run_s1b_adapter.subprocess.run=parallel
    sys.argv=['run_s1b_adapter.py','--source',str(ROOT/'inputs/recovered/Old/s1b_analysis.py'),'--input',str(ROOT/'inputs/download_snapshot/items'),'--out',str(ROOT/'historical/s1b_literal')]
    raise SystemExit(run_s1b_adapter.main())

"""Concurrency-only execution of the Cloud adapter's generated statistical script.
Original per-file loop and final report AST are unchanged; result order is sorted.
"""
from pathlib import Path
import ast,sys,json,hashlib
from concurrent.futures import ProcessPoolExecutor
WORKER=None
def prepare(source):
 src=Path(source);tree=ast.parse(src.read_text(encoding='utf-8'));main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
 g={'__name__':'cloud_parallel_execution','__file__':str(src)}
 top=ast.Module(body=[n for n in tree.body if not(isinstance(n,ast.If) and isinstance(n.test,ast.Compare))],type_ignores=[]);exec(compile(top,str(src),'exec'),g)
 files=[str(p) for p in sorted(Path(g['HERE']).glob('*.csv')) if p.name.lower() not in {s.lower() for s in g['SKIP']}];g['files']=files
 idx=next(i for i,n in enumerate(main.body) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple));original=main.body[idx]
 loop=ast.For(target=original.target,iter=ast.List(elts=[ast.Name(id='task',ctx=ast.Load())],ctx=ast.Load()),body=original.body,orelse=[])
 fun=ast.FunctionDef(name='_process_original',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='task')],kwonlyargs=[],kw_defaults=[],defaults=[]),body=ast.parse('series={}\nmeta={}').body+[loop]+ast.parse('return series,meta').body,decorator_list=[])
 module=ast.Module(body=[fun],type_ignores=[]);ast.fix_missing_locations(module);exec(compile(module,str(src),'exec'),g)
 assert isinstance(main.body[idx+1],ast.If);tail=ast.Module(body=main.body[idx+2:],type_ignores=[]);ast.fix_missing_locations(tail)
 return src,g,files,module,tail
def init(source):
 global WORKER
 WORKER=prepare(source)[1]['_process_original']
def one(task):return WORKER(task)
def main():
 src,g,files,module,tail=prepare(sys.argv[1]);out=src.parent;meta={};series={}
 (out/'parallel_original_loop.py').write_text(ast.unparse(module),encoding='utf-8');(out/'parallel_original_tail.py').write_text(ast.unparse(tail),encoding='utf-8')
 with ProcessPoolExecutor(max_workers=16,initializer=init,initargs=(str(src),)) as pool:
  for i,(s,m) in enumerate(pool.map(one,enumerate(files,1),chunksize=10),1):
   series.update(s);meta.update(m)
   if i%1000==0:print('CLOUD_ADAPTER_PARALLEL_PROGRESS',i,flush=True)
 assert series;g.update({'series':series,'meta':meta,'input':lambda *a:''});exec(compile(tail,str(src),'exec'),g)
 (out/'PARALLEL_EXECUTION.json').write_text(json.dumps({'generated_adapter_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'workers':16,'ordered_assembly':True,'statistical_changes':[],'note':'Concurrency adaptation of generated I/O-adapted recovered code; not an unmodified serial execution'},indent=2))
if __name__=='__main__':main()

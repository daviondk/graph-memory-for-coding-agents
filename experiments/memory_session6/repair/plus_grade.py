import ast
import warnings
import numpy
from concurrent.futures import ThreadPoolExecutor
from common import *
from runner import execute
warnings.simplefilter('ignore',SyntaxWarning)
def grade_plus(task):
    r,orig,enh=task;i=r['id'];entry=r['interface'].split('(')[0]
    if enh is None:return i,{'covered':False,'reason':'missing upstream ID'}
    try:
        defs=[n.name for n in ast.parse(enh['code']).body if isinstance(n,ast.FunctionDef)]
        tree=ast.parse(enh['test'])
        calls=[n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        if entry not in defs or entry not in calls:return i,{'covered':False,'reason':'public entry point mismatch'}
    except (SyntaxError,KeyError):
        return i,{'covered':False,'reason':'release parse error'}
    d=ROOT/'grading'/str(i);d.mkdir(exist_ok=True,parents=True)
    (d/'plus_reference.py').write_bytes(enh['code'].encode())
    paths={'reference':d/'reference.py','plus_reference':d/'plus_reference.py','stub':d/'stub.py'}
    paths.update({b:ROOT/path(i,b+'.py') for b in ('current','raw','note')})
    np_site=str(pathlib.Path(numpy.__file__).resolve().parent.parent)
    setup=["import os; os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['OMP_NUM_THREADS']='1'",'import sys; sys.path.append('+repr(np_site)+')']+enh['test_imports']
    cache={};ret={'covered':True}
    for b,p in paths.items():
        k=sha(p.read_bytes())
        if k not in cache:cache[k]=execute(p,entry,setup,[enh['test']])
        ret[b]=dict(code_sha=k,**cache[k])
    return i,ret
def main():
    check(read('plus_lock.json')['hashes']);check(read('prediction_lock.json')['hashes'])
    scores=read('scores.json')
    ds={r['task_id']:r for r in read('upstream-sanitized-mbpp.json')}
    enhanced={int(r['task_id']):r for l in gzip.decompress((ROOT/'mbppplus.jsonl.gz').read_bytes()).splitlines() if (r:=json.loads(l))}
    its=read('roster.json')['items']
    with ThreadPoolExecutor(max_workers=3) as pool:
        out=dict(pool.map(grade_plus,[(r,ds[r['id']],enhanced.get(r['id'])) for r in its]))
    save('plus_scores.json',out)
    print(stamp(),'enhanced coverage',sum(v['covered'] for v in out.values()),flush=True)
if __name__=='__main__':main()


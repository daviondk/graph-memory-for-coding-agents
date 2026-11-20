"""Independent zero-shot Semlith run on new Python repositories. No gold requested."""
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from run import D,R,load,now,panel_name,rows,save,sha,writegz
from native_run import load_module

def run(config):
    binary=R/'native/semlith.exe'; folder=D/'native'/config
    corpus=folder/'corpus'; db=folder/'store'; folder.mkdir(parents=True,exist_ok=True)
    os.environ.update(SEMLITH_BIN=str(binary),SEMLITH_HOME=str(folder/'home'),SEMLITH_MODEL_CACHE=str(R/'native/models'),
        SEMLITH_ACCEL='cpu',SEMLITH_EMBED_THREADS='2',SCORECARD_HOME=str(folder/'scorecard'),PYTHONUTF8='1')
    load_module('common','publisher_common.py'); arms=load_module('arms','publisher_arms.py')
    cases=[]
    for path,spec in load(D/'roster.json').items():
        p=Path(path)
        if not p.stem.startswith(config+'_test_') or 'fresh' not in spec:continue
        keep=dict(spec['fresh'])
        for j,r in enumerate(rows(p,['repo_name','code','context'])):
            if j in keep:cases.append((panel_name(p.stem),keep[j],r))
    for i,(_,_,r) in enumerate(cases):
        here=corpus/f'i{i:05d}';here.mkdir(parents=True,exist_ok=True)
        for j,doc in enumerate(r['context']):(here/f'c{j:03d}.py').write_text(doc,encoding='utf8',newline='\n')
    t=time.monotonic()
    with (folder/'index.log').open('wb') as f:
        subprocess.run([str(binary),'index','--store',str(db),str(corpus)],stdout=f,stderr=f,timeout=2400,check=True)
    index_time=time.monotonic()-t; t=time.monotonic()
    mcp=arms.SemlithMCP(str(db));out=[]
    try:
        for i,(p,j,r) in enumerate(cases):
            n=len(r['context']);q='\n'.join(r['code'].splitlines()[-3:]); order=[]
            found=mcp.search(q,k=n+10,paths=[f'i{i:05d}/**'])
            for hit in found:
                name=Path(hit.path)
                assert name.parent.name==f'i{i:05d}' and name.stem[0]=='c'
                k=int(name.stem[1:]);assert 0<=k<n
                if k not in order:order.append(k)
            rank=order+[k for k in range(n) if k not in order]
            out.append([p,j,r['repo_name'],len(order),rank])
    finally:mcp.close()
    filename='native_'+config+'.jsonl.gz';writegz(filename,out)
    return dict(config=config,n=len(out),sha=sha(D/filename),file=filename,index_s=index_time,query_s=time.monotonic()-t)

if __name__=='__main__':
    save('native_lock.json',dict(utc=now(),roster=sha(D/'roster.json'),protocol=sha(D/'TRANSFER_ADDENDUM_RU.md'),
       source=sha(D/'native_transfer.py'),binary=sha(R/'native/semlith.exe'),rpc=sha(R/'publisher_arms.py'),
       model_files={x.name:sha(x) for x in (R/'native/models').rglob('*') if x.is_file()}))
    with ProcessPoolExecutor(2) as pool:res=list(pool.map(run,['python_cff','python_cfr']))
    save('native_decision_lock.json',dict(utc=now(),configurations=res,method=sha(D/'native_lock.json')))
    print(res,flush=True)

"""Evaluate sealed source coordinates and ranks under the published three-way mode split."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip
import hashlib
import json
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SERIES=ROOT.parent
COHORT=SERIES.parent/'graph_memory_round18/isetrace_official/cohort.json'
GOLD=ROOT/'cpu_fallback/inputs/test-gold.json.gz'
ORDER=['direct_recall','linked_recall','multi_fact_recall']
NAMES=['full_support','coverage']
def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
def h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,record):
    raw=(json.dumps(record,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw)
def freeze():
    assert not (HERE/'plan.json').exists()
    put(HERE/'plan.json',{'code':h(HERE/'modes.py'),'protocol':h(HERE/'PROTOCOL_RU.md'),
        'cohort':h(COHORT),'gold':h(GOLD),'B':10000,'seed':13})

def benchmark(tag):
    md={r['query_id']:r for r in read(COHORT)}
    c=Counter(r['memory_mode'] for r in md.values());assert [c[k] for k in ORDER]==[641,906,453]
    gold=read(GOLD);assert set(gold)==set(md)
    info={q:{'q':q,'t':r['trajectory_id'],'mode':r['memory_mode'],'n_events':len({s['event_id'] for s in gold[q]})} for q,r in md.items()}
    cont={m:dict(sorted(Counter('1' if x['n_events']==1 else '2' if x['n_events']==2 else '3+' for x in info.values() if x['mode']==m).items())) for m in ORDER}
    assert sum(sum(r.values()) for r in cont.values())==2000
    if tag=='factor_hash64':
        path=SERIES/'factor_reader/hash64-outcomes.json.gz';r=read(path)
        A,B=r['prefix/degree'],r['prefix/dense']
    else:
        no_next=tag.startswith('no_next_')
        panel=tag.replace('no_next_','')
        parent=ROOT if panel=='full' else ROOT/'cpu_fallback'/panel
        path=(ROOT/'adjacency_control'/panel if no_next else parent)/'outcomes.json.gz'
        def arm(file,model):
            return {r['q']:r for r in read(file) if r.get('stage','test')=='test' and r['method']==model and r['arm']=='prefix'}
        A=arm(path,'rgcn');B=arm(parent/'outcomes.json.gz','rgcn' if no_next else 'seed')
    assert set(info)==set(A)==set(B)
    for q,row in info.items():
        assert row['t']==A[q]['t']==B[q]['t']
        row['A']={n:A[q][n] for n in NAMES};row['B']={n:B[q][n] for n in NAMES}
    return info,cont,h(path)

def estimates(v):
    # Seeds of the separate models are held fixed; inference unit is question, repeated unit trajectory.
    rates = v[...,1:]/v[...,:1]
    return rates[...,:2],rates[...,2:4],rates[...,:2]-rates[...,2:4]

def run(tag):
    plan=read(HERE/'plan.json')
    assert h(HERE/'modes.py')==plan['code'] and h(COHORT)==plan['cohort'] and h(GOLD)==plan['gold']
    source,tbl,sha=benchmark(tag)
    grouped=defaultdict(lambda:np.zeros((3,5)))
    for r in source.values():
        i=ORDER.index(r['mode'])
        grouped[r['t']][i] += [1.,r['A']['full_support'],r['A']['coverage'],r['B']['full_support'],r['B']['coverage']]
    arr=np.stack([grouped[t] for t in sorted(grouped)])
    av,bv,delta=estimates(arr.sum(axis=0))
    rng=np.random.default_rng(13);sims=[]
    for i in range(0,10000,64):
        indices=rng.integers(0,len(arr),size=(min(10000-i,64),len(arr)))
        sims.append(estimates(arr[indices].sum(axis=1))[2])
    sim=np.concatenate(sims)
    ci=np.quantile(sim,[.025,.975],axis=0)
    difference=delta[2]-delta[0]
    uncertainty=np.quantile(sim[:,2]-sim[:,0],[.025,.975],axis=0)
    column=lambda d,interval:dict(estimate=float(d),ci95=interval.tolist())
    g={m:{n:{'a':float(av[i,j]),'b':float(bv[i,j]),**column(delta[i,j],ci[:,i,j])} for j,n in enumerate(NAMES)}
       for i,m in enumerate(ORDER)}
    sensitivity={n:column(difference[j],uncertainty[:,j]) for j,n in enumerate(NAMES)}
    of=HERE/f'{tag}-data.json.gz';put(of,[source[q] for q in sorted(source)])
    put(HERE/f'{tag}-results.json',dict(source=sha,data=h(of),plan=h(HERE/'plan.json'),contingency=tbl,groups=g,
        multi_minus_direct=sensitivity,trajectory_count=len(arr)))
    print(tag,tbl,[(m,g[m]['full_support']) for m in ORDER],sensitivity['full_support'],flush=True)
if __name__=='__main__':
    if sys.argv[1]=='lock':freeze()
    else:run(sys.argv[1])

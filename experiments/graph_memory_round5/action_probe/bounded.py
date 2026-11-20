import importlib.util,sys,base64,hashlib,gzip
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
spec=importlib.util.spec_from_file_location('r5_observation',Path(__file__).with_name('policy.py'));pol=importlib.util.module_from_spec(spec);spec.loader.exec_module(pol)
from schema_codec import memory,prior,encode,decode,anchor
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from acquire import D,W,write,rr,read,save,h,stamp
import re,numpy as np
ARMS=('base','address','offset','lru_editor','lru_address')
def rule(a):return 'dict_lru' if a.startswith('lru_') else 'cal_neighbor'
def run(shard):
    pairs=dict(rr(D/'raw_pairs.jsonl.gz'))
    memory.pack=lambda state,_:encode(state,'zstd15','json');memory.unpack=lambda b,_:decode(b)
    ws=anchor.weights();cost={a:Counter() for a in ARMS}
    with gzip.open(D/f'bounded_cuts_{shard}.gz','wt',encoding='utf8') as g,gzip.open(D/f'bounded_steps_{shard}.gz','wt',encoding='utf8') as log:
        for task in rr(W/f'source_{shard}.jsonl.gz'):
            iid=task['instance'];static={k:task[k] for k in ('instance','issue')};states={a:bytes([1])+memory.initial(rule(a)) for a in ARMS}
            for j,(ev,extra) in enumerate(zip(task['events'],pairs[iid]),1):
                details={}
                for a in ARMS:
                    root=bool(states[a][0]);extra_lines=pol.readlines(extra,root)
                    if extra:
                        cmd=extra['command'];root=False if re.search(r'(?:^|[;&\n])\s*(?:cd|pushd|popd)\b',cmd) else root
                        if re.fullmatch(r'\s*cd\s+/testbed/?\s*',cmd):root=True
                    def ingest(s,meta,e,t):
                        anchor.anchored_advance(s,meta,e,t)
                        if a in ('address','offset','lru_address'):
                            coordinates={}
                            for p,n,value,_ in extra_lines:
                                z=n+int(a=='offset');s['rebase'].setdefault(p,{})[z]=[value,t]
                                coordinates.setdefault(p,[]).append(z)
                            for p,ns in coordinates.items():
                                meta['paths'][p]=t;meta['visits'][p]+=1;meta['center'][p]=(min(ns)+max(ns))*.5
                    prior.advance=ingest
                    b,fit=memory.transition(rule(a),states[a][1:],ev,static,ws,4095)
                    states[a]=bytes([int(root)])+b;size=len(states[a]);assert size<=4096 and fit[1]+1==size
                    details[a]=[size,h(states[a])];cost[a]['bytes']+=size;cost[a]['steps']+=1;cost[a]['max']=max(cost[a]['max'],size)
                write(log,[iid,j,details])
                if j%4==0 and j<len(task['events']):write(g,[iid,j,{a:base64.b64encode(v).decode('ascii') for a,v in states.items()}])
    return cost
def score():
    spec=importlib.util.spec_from_file_location('r5_unbounded_evaluation',D/'score.py');sc=importlib.util.module_from_spec(spec);spec.loader.exec_module(sc)
    locked=read(D/'bounded_lock.json')
    assert all(h((D/f).read_bytes())==x for f,x in locked['files'].items())
    marks={(r['id'],r['cut']):r for r in rr(D/'items.jsonl.gz') if r['point']=='cut'}
    prev={(i,t):v['generic'][0] for i,repo,t,n,v in rr(W/'scored.jsonl.gz')};records=[]
    for k in range(8):
        cuts=iter(rr(D/f'bounded_cuts_{k}.gz'))
        for task in rr(W/f'source_{k}.jsonl.gz'):
            iid=task['instance'];ev=task['events']
            for t in range(4,len(ev),4):
                i,j,pack=next(cuts);assert (i,j)==(iid,t)
                if (iid,t) not in marks:continue
                z=marks[iid,t];a,obs=anchor.future_check(ev,t);lo,ls=anchor.invert(a,obs)
                methods={}
                for name,b in pack.items():
                    blob=base64.b64decode(b);assert len(blob)<=4096;x=decode(blob[1:]);assert x[1]==t
                    f=prior.materialize(x)[1]['rebase'].get(z['path'],{})
                    hits=sum(f.get(lo+i,[None])[0]==s for i,s in enumerate(ls));methods[name]=dict(hits=hits,full=hits==len(ls))
                records.append(dict(id=iid,repo=task['official_repo'],cut=t,lines=len(ls),methods=methods,old_full=prev[iid,t]))
        assert next(cuts,None) is None
    with gzip.open(D/'bounded_items.jsonl.gz','wt',encoding='utf8') as g:
        for r in records:write(g,r)
    save('bounded_results.json',dict(n=len(records),counts={a:sum(r['methods'][a]['full'] for r in records) for a in ARMS},frac={a:np.mean([r['methods'][a]['hits']/r['lines'] for r in records]) for a in ARMS},paired={a+'-'+b:sc.effect(records,a,b) for a,b in [('address','base'),('address','offset'),('lru_address','lru_editor'),('address','lru_address')]},control_old_mismatch=sum(r['old_full']!=r['methods']['base']['full'] for r in records),cost=locked['cost'],items=h((D/'bounded_items.jsonl.gz').read_bytes())))
if __name__=='__main__':
    if sys.argv[1]=='predict':
        save('bounded_method_lock.json',dict(utc=stamp(),sources={str(p):h(p.read_bytes()) for p in (D/'BOUNDED_PROTOCOL.md',D/'LRU_AMENDMENT.md',D/'bounded.py',D/'policy.py',W/'schema_codec.py')}))
        with ProcessPoolExecutor(4) as pool:cost=list(pool.map(run,range(8)))
        save('bounded_lock.json',dict(utc=stamp(),cost=cost,files={p.name:h(p.read_bytes()) for p in list(D.glob('bounded_cuts_*.gz'))+list(D.glob('bounded_steps_*.gz'))}))
    else:score()


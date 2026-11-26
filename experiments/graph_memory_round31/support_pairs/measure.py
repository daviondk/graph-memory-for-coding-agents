"""Compare every supported withdrawal set against the entire ranked pair table."""
from collections import defaultdict
from functools import lru_cache
from itertools import combinations
from math import comb
from time import perf_counter_ns
import numpy as np
from families import decision_family,linear_family,failures
from prepare import ROOT,get,put,sha
def benchmark(rows,mode):
    edges=rows["pairs"][mode];doc_order=rows["docs"];n=len(doc_order)
    mapped=np.asarray([(1<<a)|(1<<b) for a,b in edges],dtype=np.int32)
    bans=failures(n);event_sizes=np.asarray([k for k,mask in bans]);masks=np.asarray([mask for k,mask in bans],dtype=np.int32)
    legal=(masks[:,None]&mapped[None,:])==0
    winner=np.where(legal.any(axis=1),legal.argmax(axis=1),-1)
    out={}
    for f in (1,2,3):
        cap=min(len(edges),comb(2+f,2))
        start=perf_counter_ns();tree,steps=decision_family(edges,f);tree_time=perf_counter_ns()-start
        start=perf_counter_ns();linear=linear_family(edges,n,f);linear_time=perf_counter_ns()-start
        actual=set(int(i) for i in winner[event_sizes<=f] if i>=0)
        assert set(tree)==actual and actual<=set(linear) and len(linear)<=cap
        top=set(doc_order[:2+f])
        doc_cache=[i for i,(a,b) in enumerate(edges) if a in top and b in top]
        assert len(doc_cache)==cap
        prev,_=decision_family(edges,max(0,f-1))
        completed=set(prev)
        for i in range(len(edges)):
            if len(completed)==cap:break
            completed.add(i)
        methods={"all":list(range(len(edges))),"raw":list(range(cap)),"raw_matched":list(range(len(tree))),
                 "doc_prefix":doc_cache,"previous_plus_raw":sorted(completed),"linear":linear,"tree":tree}
        by_method={}
        for name,indices in methods.items():
            stored=legal[:,indices];returned=np.where(stored.any(axis=1),np.array(indices)[stored.argmax(axis=1)],-1)
            is_exact=winner==returned
            if name in ("all","linear","tree") or (name=="doc_prefix" and mode=="add"):assert is_exact[event_sizes<=f].all()
            per_size=[]
            for k in range(4):
                sel=event_sizes==k
                if not np.any(sel):per_size.append(None);continue
                hits=int(is_exact[sel].sum());wrong_value=int(((returned[sel]>=0)&(~is_exact[sel])).sum())
                first=np.where(stored.any(axis=1),stored.argmax(axis=1)+1,len(indices))
                per_size.append([int(sel.sum()),hits,wrong_value,int(first[sel].sum())])
            by_method[name]=[len(indices),per_size]
        out[str(f)]={"stats":by_method,"construct":[steps,tree_time,linear_time],"tree":tree,"linear":linear}
    return out
def main():
    rankings=get(ROOT/"rankings.json.gz")
    seal=get(ROOT/"ranking-seal.json");assert sha(ROOT/"rankings.json.gz")==seal["rankings"]
    plan={"protocol":sha(ROOT/"PROTOCOL_RU.md"),"rankings":seal["rankings"],"algorithm":sha(ROOT/"families.py"),"code":sha(ROOT/"measure.py")}
    put(ROOT/"measurement-plan.json",plan)
    metrics={}
    for i,(q,record) in enumerate(rankings.items()):
        metrics[q]={m:benchmark(record,m) for m in ("add","joint")}
        if (i+1)%1000==0:print(i+1,flush=True)
    put(ROOT/"cache-measurements.json.gz",metrics)
    put(ROOT/"measurement-seal.json",{"plan":sha(ROOT/"measurement-plan.json"),"measurements":sha(ROOT/"cache-measurements.json.gz")})
if __name__=="__main__":main()

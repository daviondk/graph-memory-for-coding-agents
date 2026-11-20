"""Replay bounded write/read policies. Run with the name of a completed cohort."""
import base64
import collections
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
from sketch import encoded,decoded,layout,has,addresses
ROOT=Path(__file__).resolve().parent


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p,data):
    p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf8")


def pack(p,obj):
    p.write_bytes(gzip.compress(json.dumps(obj,separators=(",",":")).encode(),mtime=0))


def run(name):
    assert name in ("testmemory","testmemory_compat","testmemory_holdout")
    src=ROOT.parent/name
    out=ROOT/name
    out.mkdir(exist_ok=True)
    inputs=[src/"graphs.json.gz",src/"outcomes.json",ROOT/"PROTOCOL.md",ROOT/"sketch.py",Path(__file__).resolve()]
    graphs=json.loads(gzip.decompress(inputs[0].read_bytes()))
    cases=json.loads(inputs[1].read_bytes())
    future={(r["task"],r["direction"],r["node"]):r for r in cases}
    # Obtain the full old test inventory even when a later compatibility check excludes a case.
    rows=[];blobs=[];alloc=[]
    for g in graphs:
        task,direction=g["task"],g["direction"]
        nodes=sorted(json.loads((src/"runs"/task/"nodes.json").read_bytes()))
        shared=set(g["edges"].get("shared",[]))
        previous=[set(g["edges"].get(node,[]))|shared for node in nodes]
        for b in (64,256):
            budget=b*len(nodes)
            proposals=layout(previous,budget)
            for mode,(pred,tag,sizes,ks,_) in proposals.items():
                alloc.append(dict(task=task,direction=direction,capacity=b,mode=mode,tag=tag,expected=pred,sizes=sizes,hashes=ks))
            for seed in range(32):
                memo={}
                for mode,plan in proposals.items():
                    tag=plan[1]
                    if tag not in memo:
                        state=encoded(plan,seed)
                        assert len(state)<=budget
                        fields=decoded(state,len(nodes))
                        memo[tag]=(state,[has(fields,i,g["changed"],seed) for i in range(len(nodes))])
                    state,predicted=memo[tag]
                    if seed==0:
                        blobs.append(dict(task=task,direction=direction,capacity=b,mode=mode,nodes=nodes,data=base64.b64encode(state).decode()))
                    for i,node in enumerate(nodes):
                        actual=bool(previous[i]&set(g["changed"]))
                        assert predicted[i] or not actual
                        q=(task,direction,node)
                        if q not in future:continue
                        f=future[q]
                        assert actual==f["selected"]["symbol"]
                        rows.append([task,direction,node,b,seed,mode,int(predicted[i]),int(actual),int(f["changed"])])
                addresses.cache_clear()
    pack(out/"rows.json.gz",rows);pack(out/"payloads.json.gz",blobs);save(out/"allocations.json",alloc)
    agg=collections.defaultdict(lambda:[0,0,0,0])
    for t,d,node,b,s,m,p,exact,flip in rows:
        cnt=agg[b,s,m]
        cnt[0]+=1;cnt[1]+=p;cnt[2]+=p-exact;cnt[3]+=int(flip and not p)
    result={}
    for cap in (64,256):
        band={}
        for m in ("fixed","adaptive_flat","factored","selected"):
            n,r,extra,miss=agg[cap,0,m]
            exc=[agg[cap,s,m][2] for s in range(32)]
            band[m]=dict(n=n,reruns=r,extra=extra,stale=miss,mean_extra_32=statistics.mean(exc),min_extra=min(exc),max_extra=max(exc))
        grouped=collections.defaultdict(lambda:collections.Counter())
        for t,d,node,b,s,m,p,exact,flip in rows:
            if b==cap and s==0 and m in ("adaptive_flat","selected"):
                grouped[t][m]+=p
                if m=="selected":grouped[t]["n"]+=1
        vals=[(x["selected"]-x["adaptive_flat"],x["n"]) for x in grouped.values()]
        rng=random.Random(19021);dist=[]
        for j in range(10000):
            a,b=map(sum,zip(*rng.choices(vals,k=len(vals))));dist.append(a/b)
        dist.sort()
        band["selected_minus_flat_ci"]=[dist[249],dist[9749]]
        result[cap]=band
    save(out/"results.json",result)
    files={str(p.relative_to(ROOT.parent)) if p.is_relative_to(ROOT.parent) else p.name:digest(p) for p in inputs}
    save(out/"verification.json",dict(inputs=files,cases=len(cases),observations=len(rows),salt_count=32,
        represented=len(blobs),no_missed_exact_intersection=True,bytes_checked=True,
        outputs={p.name:digest(p) for p in (out/"rows.json.gz",out/"payloads.json.gz",out/"allocations.json",out/"results.json")}))
    print(name,json.dumps(result))
if __name__=="__main__":run(sys.argv[1])

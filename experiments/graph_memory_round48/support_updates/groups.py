"""Apply whole support-count transactions on one causally masked candidate pool."""
from collections import Counter,defaultdict
from contextlib import closing
from hashlib import sha256
import gzip,json
import sqlite3
import numpy as np
from replay import DB,FIXTURE,HERE,SCALE,Snapshot,library,packet_ids,save,value
def execute(c,lib,q,info):
    vis=dict(info["sources"])
    pos=dict(c.execute("SELECT source,position FROM origin WHERE q=?",(q,)))
    owners={p[0]:i for i,p in enumerate(info["producers"])}
    refs=defaultdict(set)
    for i,s in c.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):refs[i].add(s)
    candidates=[]
    for i,h,cost in c.execute("SELECT id,node_hash,tokens FROM node WHERE q=?",(q,)):
        if refs[i]:
            sources=refs[i];used={owners[s] for s in sources if s in owners}
            candidates.append((max(vis[s] for s in sources),(-max(pos[s] for s in sources),-min(pos[s] for s in sources),h),i,cost,used))
    old=Counter();results=[]
    for step,(_,_,deltas,*_) in enumerate(info["steps"],1):
        available=sorted((item for item in candidates if item[0]<=step),key=lambda a:a[1])
        for cap in (1,4):
            delta={i:value(b,cap)-value(a,cap) for i,a,b in deltas}
            obs=[(i,c,(SCALE+r//2)//r+sum(value(old[s],cap) for s in links),links)
                 for r,(_,_,i,c,links) in enumerate(available,1)]
            def solve(allowed):
                arr=[(i,cost,u+sum(delta.get(s,0) for s in links if s in allowed)) for i,cost,u,links in obs]
                snap=Snapshot(arr)
                blob=snap.native(lib,[0]*snap.n)(0,0)
                return snap,packet_ids(blob)
            snap,base=solve(set())
            _,after=solve(set(delta))
            singles={i:solve({i})[1] for i in delta}
            selected=set(base);head=set(snap.head)
            violation=[]
            for i,cost,u,links in obs:
                if i in head or cost>snap.cap:continue
                shift=sum(delta.get(s,0) for s in links)
                if (i in selected and shift<0) or (i not in selected and shift>0):violation.append(i)
            safe=not violation
            assert not safe or base==after
            results.append(dict(step=step,cap=cap,count=len(deltas),effective=sum(bool(x) for x in delta.values()),
                                base=base,after=after,single_same=sorted(i for i,ans in singles.items() if ans==base),
                                signs_safe=safe,sign_blockers=violation))
        for i,a,b in deltas:
            assert old[i]==a;old[i]=b
    return results
def summarize(data):
    out={}
    for cap in (1,4):
        rows=[row for group in data.values() for row in group if row["cap"]==cap]
        groups={}
        for label,sub in [("all",rows),("joint",[r for r in rows if r["count"]>=2]),("single",[r for r in rows if r["count"]==1]),("unchanged_counts",[r for r in rows if not r["count"]])]:
            groups[label]=dict(n=len(sub),changed=sum(r["base"]!=r["after"] for r in sub),
                              only_joint=sum(r["base"]!=r["after"] and len(r["single_same"])==r["count"] for r in sub),
                              certified=sum(r["signs_safe"] for r in sub),
                              not_certified_but_equal=sum(not r["signs_safe"] and r["base"]==r["after"] for r in sub))
        clusters=np.array([[sum(1 for r in states if r["cap"]==cap and r["count"]>=2),
                            sum(1 for r in states if r["cap"]==cap and r["count"]>=2 and r["base"]!=r["after"])]
                            for states in data.values()],dtype=np.int64)
        ids=np.random.default_rng(48020).integers(0,len(data),(10000,len(data)))
        sums=clusters[ids].sum(axis=1);valid=sums[:,0]>0
        groups['joint']['changed_ci_percent']=np.percentile(100*sums[valid,1]/sums[valid,0],[2.5,97.5]).tolist()
        out[cap]=groups
    return out
if __name__=="__main__":
    lib=library();fixture=json.loads(gzip.decompress(FIXTURE.read_bytes()))
    with closing(sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True)) as c:
        result={q:execute(c,lib,q,info) for q,info in sorted(fixture["queries"].items())}
    save("group-packets.json.gz",result)
    report=summarize(result);report["protocol_sha256"]=sha256((HERE/"GROUP_CONTROL_RU.md").read_bytes()).hexdigest()
    (HERE/"group-results.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8");print(report)

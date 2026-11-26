"""Independent grading, paired trajectory inference, and audit of the semantic-head order."""
from collections import defaultdict
from pathlib import Path
from statistics import median
import sys
import numpy as np
D=Path(__file__).resolve().parent
S=D.parent/"stream_packet"
sys.path.insert(0,str(S))
from fixture import load,save,digest

def exact(rows,updates,step,cap):
    active=[r for r in rows if r[0]<=step]
    counts=dict(x for group in updates[:step] for x in group)
    head=[]
    room=2048
    for r in sorted(active,key=lambda r:r[1]):
        if room-r[2]<1024:
            break
        head.append(r[1])
        room-=r[2]
    eligible=[r for r in active if r[1] not in head]
    dp=[(0,0)]*(room+1)
    for j,(_,_,cost,val,owners) in enumerate(eligible):
        u=val+sum(min(cap,counts.get(a,0))<<28 for a in owners)
        for b in range(room,cost-1,-1):
            old,mask=dp[b-cost]
            if old+u>dp[b][0]:
                dp[b]=old+u,mask|(1<<j)
    return head+[r[1] for j,r in reversed(list(enumerate(eligible))) if dp[room][1]>>j&1]

def main():
    inputs=load(S/"input.json.gz")
    marks=load(S/"judgments.json.gz")
    orders=load(D/"packets.json.gz")
    ref=load(S/"packets.json.gz")
    specs=load(D/"forecast-seal.json")
    assert digest((D/"packets.json.gz").read_bytes())==specs["packets"]
    assert digest((D/"timing.json.gz").read_bytes())==specs["times"]
    assert digest((D/"stream.cpp").read_bytes())==specs["source"]
    groups={g:i for i,g in enumerate(sorted({v[0] for v in inputs.values()}))}
    n=len(groups)
    rng=np.random.default_rng(49171)
    boot=rng.multinomial(n,np.full(n,1/n),size=10000).astype(float)
    def ci(x):return np.percentile(x,[2.5,97.5]).tolist()
    buckets=defaultdict(list)
    sample=set(sorted(inputs,key=lambda q:digest(("semantic-audit/"+q).encode()))[:32])
    trials=defaultdict(list);costs={};matrices={}
    for q,r,mode,cap,ns,visited,redo,peak in load(D/"timing.json.gz"):
        key=q,mode,cap
        trials[key].append((r,ns))
        assert costs.setdefault(key,(visited,redo,peak))==(visited,redo,peak)
    runtime={}
    for mode in (0,-1,16):
        for cap in (0,4):
            m=np.zeros(n);peak=[];v=0;r=0
            for q,(tr,_,_) in inputs.items():
                key=q,mode,cap
                vals=sorted(trials[key])
                assert [i for i,x in vals]==[1,2,3,4,5]
                m[groups[tr]]+=median([x for i,x in vals])
                visits,rewind,pk=costs[key];v+=visits;r+=rewind;peak.append(pk)
            matrices[mode,cap]=m
            runtime[f"{mode}/{cap}"]=dict(ms=m.sum()/1e6,rows=v,rewound=r,median_dp_bytes=median(peak))
    for mode in (-1,16):
        for cap in (0,4):
            a=matrices[0,cap];b=matrices[mode,cap]
            rr=runtime[f"{mode}/{cap}"];rr.update(ratio=a.sum()/b.sum(),ci=ci((boot@a)/(boot@b)))
            if mode==16:
                a=matrices[-1,cap];rr.update(vs_terminal=a.sum()/b.sum(),terminal_ci=ci((boot@a)/(boot@b)))
    audited=0
    for q,(tr,rows,ev) in inputs.items():
        meta={r[1]:r for r in rows}
        for stage,step in (("final",len(ev)),("eight",8)):
            if step>len(ev):continue
            judge=marks[q]
            ids={str(cap):orders[q][str(cap)][str(step)] for cap in (0,4)}
            ids["dense"]=ref[q][str(step)]["dense"]
            for j,name in enumerate(("0","4","dense")):
                order=ids[name];chosen=set(order)
                assert len(chosen)==len(order) and all(meta[i][0]<=step for i in chosen)
                cost=sum(meta[i][2] for i in chosen);assert cost<=2048
                total=sum(w for w,owners in judge)
                covered=sum(w for w,owners in judge if chosen.intersection(owners))
                buckets[stage,name].append([groups[tr],int(covered==total),covered/total,cost])
                if q in sample and name!="dense":
                    assert order==exact(rows,ev,step,int(name));audited+=1
    metrics={}
    for stage in ("eight","final"):
        cm={}
        for name in ("0","4","dense"):
            m=np.zeros((n,4))
            for k,full,coverage,cost in buckets[stage,name]:m[k]+=(1,full,coverage,cost)
            cm[name]=m
        row={"n":int(cm["0"][:,0].sum())}
        for name,m in cm.items():
            count,full,cov,cost=m.sum(axis=0)
            row[name]=dict(full=full/count,coverage=cov/count,tokens=cost/count)
            diff=m[:,1]-cm["dense"][:,1]
            row[name].update(delta_pp=100*diff.sum()/count,ci=ci(100*(boot@diff)/(boot@m[:,0])))
        metrics[stage]=row
    out=dict(runtime=runtime,metrics=metrics,audited=audited)
    save(D/"results.json",out)
    print(metrics,runtime["16/0"],runtime["16/4"],audited)
if __name__=="__main__":
    main()

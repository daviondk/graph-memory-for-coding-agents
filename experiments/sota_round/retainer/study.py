"""MSR range-cache replay. Original source data and code are pinned by fetch.py."""
import csv
import gzip
import hashlib
import io
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np
from fetch import HERE, RAW, digest
from upstream.s3fifo import S3FIFO

RESULTS = HERE / "results"
CAPACITIES = (128, 512, 2048)

def read_ranges(volume):
    buf=gzip.decompress((RAW/(volume["volume"]+".csv.gz")).read_bytes())
    assert digest(buf)==volume["read_projection_sha256"]
    result=[]
    for line in buf.splitlines():
        _,offset,size=map(int,line.split(b","))
        assert size>0 and offset>=0
        result.append(range(offset//4096,(offset+size-1)//4096+1))
    assert len(result)==32768
    return result

def group_masks(pages):
    masks={}
    for page in pages:
        g=page//4
        masks[g]=masks.get(g,0)|(1<<(page%4))
    return masks

def group_stats(ranges):
    counts=Counter(); masks={}
    for pages in ranges:
        counts.update(pages)
        for group,pattern in group_masks(pages).items():
            if group not in masks: masks[group]=Counter()
            masks[group][pattern]+=1
    return counts,masks

def joint_mask_curves(patterns):
    curves={}
    for g,counts in patterns.items():
        gains=[sum(n for required,n in counts.items() if required & ~mask == 0) for mask in range(16)]
        # Tuple order makes ties prefer low numeric masks.
        curves[g]=[max((gains[m],-m) for m in range(16) if m.bit_count()==k) for k in range(5)]
    return curves

def joint_sets(curves, budgets):
    # A solution uses at most K non-empty groups. For each cardinality k its
    # group can be exchanged with an unused top-K group of no smaller benefit.
    cap=max(budgets)
    pool=set()
    for k in range(1,5):
        pool.update(sorted(curves,key=lambda g:(-curves[g][k][0],g))[:cap])
    groups=sorted(pool)
    best=np.zeros(cap+1,np.int64); choices=np.zeros((len(groups),cap+1),np.int8)
    for row,g in enumerate(groups):
        prev=best.copy()
        for k in range(1,5):
            gain,negmask=curves[g][k]
            if gain==0: continue
            candidate=prev[:-k]+gain
            better=candidate>best[k:]
            best[k:][better]=candidate[better]
            choices[row,k:][better]=-negmask
    sets={}
    for budget in budgets:
        remaining=budget; chosen=set()
        for row in range(len(groups)-1,-1,-1):
            m=int(choices[row,remaining]); remaining-=m.bit_count()
            chosen.update(groups[row]*4+i for i in range(4) if m & (1<<i))
        assert len(chosen)<=budget
        sets[budget]=chosen
    return sets

def build(hist,budgets):
    counts,patterns=group_stats(hist)
    freq=sorted(counts,key=lambda p:(-counts[p],p))
    whole=sorted(patterns,key=lambda g:(-sum(patterns[g].values()),g))
    joint=joint_sets(joint_mask_curves(patterns),budgets)
    return {k:{"joint":joint[k],"marginal":set(freq[:k]),"whole":{g*4+i for g in whole[:k//4] for i in range(4)}} for k in budgets}

class LRU:
    def __init__(self,cap):
        self.cap=cap; self.cache=OrderedDict()
    def get(self,p):
        if p in self.cache:
            self.cache.move_to_end(p); return True
        return None
    def put(self,p,_):
        self.cache[p]=True
        if len(self.cache)>self.cap: self.cache.popitem(last=False)

def replay(ranges,pins,dynamic_slots,kind,at):
    cache=(S3FIFO(dynamic_slots) if kind=="s3" else LRU(dynamic_slots)) if dynamic_slots else None
    rows=[]
    for pos,pages in enumerate(ranges):
        misses=[p for p in pages if p not in pins and (cache is None or cache.get(p) is None)]
        if cache is not None:
            for p in misses:cache.put(p,True)
        if pos>=at:
            grouped=len({p//4 for p in misses})
            rows.append((grouped,len(misses),len(pages)))
    return np.asarray(rows,np.int32)

def summarize(a):
    return {"n":len(a),"underlying_reads":int(a[:,0].sum()),"page_misses":int(a[:,1].sum()),"page_accesses":int(a[:,2].sum()),"all_hit":int((a[:,1]==0).sum()),"within_one":int((a[:,0]<=1).sum())}

def volume_run(v):
    name=v["volume"]; data=read_ranges(v); out=[]
    fits=build(data[:8192],[256,512])
    final=build(data[:16384],[128,256,512,2048])
    choices={}; validation={}
    for fam in ("joint","marginal"):
        by={}
        for slots in (0,256,512):
            pin=fits[slots][fam] if slots else set()
            a=replay(data[:16384],pin,512-slots,"s3",8192)
            by[slots]=int(a[:,0].sum())
        choices[fam]=min(by,key=by.get);validation[fam]=by
    for cap in CAPACITIES:
        plans=[("joint",final[cap]["joint"],0,"none"),("marginal",final[cap]["marginal"],0,"none"),("whole",final[cap]["whole"],0,"none"),("s3fifo",set(),cap,"s3"),("lru",set(),cap,"lru")]
        if cap==512:
            for fam in choices:
                for label,slots in [("half",256),("selected",choices[fam])]:
                    pin=final[slots][fam] if slots else set()
                    plans.append((fam+"_"+label,pin,cap-slots,"s3"))
        trace={}
        for alg,pin,slots,kind in plans:
            k=(frozenset(pin),slots,kind)
            if k not in trace:
                trace[k]=replay(data,pin,slots,kind,16384)
            a=trace[k]; pin_groups=len({p//4 for p in pin})
            out.append(dict(volume=name,cap=cap,policy=alg,pins=len(pin),pin_groups=pin_groups,dynamic_slots=slots,**summarize(a)))
            digest_bytes=a.astype("<u4").tobytes()
            # Repeated exact outputs are deduplicated by hash in the audit data.
            outputs=RESULTS/"steps"; outputs.mkdir(exist_ok=True,parents=True)
            record=hashlib.sha256(digest_bytes).hexdigest()
            path=outputs/(record+".gz")
            if not path.exists():path.write_bytes(gzip.compress(digest_bytes,mtime=0))
            out[-1]["step_log"]=record
    return {"volume":name,"n_fit":8192,"n_validation":8192,"n_test":16384,"choices":choices,"validation_group_reads":validation,"scores":out}

def analyze(rows):
    qs=[]
    control=[]
    for cap in CAPACITIES:
        for name in ("joint","marginal","whole","lru","s3fifo","joint_half","marginal_half","joint_selected","marginal_selected"):
            selected=[r for r in rows if r["cap"]==cap and r["policy"]==name]
            if not selected:continue
            n=sum(r["n"] for r in selected)
            qs.append({"cap":cap,"policy":name,"server_count":len(selected),"n":n,
              "reads_per_request":sum(r["underlying_reads"] for r in selected)/n,
              "page_miss_fraction_macro":sum(r["page_misses"]/r["page_accesses"] for r in selected)/len(selected),
              "page_miss_fraction_micro":sum(r["page_misses"] for r in selected)/sum(r["page_accesses"] for r in selected),
              "all_hit":sum(r["all_hit"] for r in selected)/n,"within_one":sum(r["within_one"] for r in selected)/n,
              "charged_reads":sum(r["underlying_reads"]+r["pin_groups"] for r in selected)/n})
        contrasts=[("joint","marginal"),("joint","s3fifo"),("joint","whole"),("joint","lru")]
        if cap==512: contrasts+=[("joint_selected","s3fifo"),("joint_selected","marginal_selected"),("joint_half","marginal_half")]
        for a,b in contrasts:
            match={r["volume"]:r for r in rows if r["cap"]==cap and r["policy"]==b}
            selected=[r for r in rows if r["cap"]==cap and r["policy"]==a]
            d=np.array([(match[r["volume"]]["underlying_reads"]-r["underlying_reads"])/r["n"] for r in selected])
            rng=np.random.default_rng(327816);draws=rng.choice(d,(10000,len(d)),replace=True).mean(axis=1)
            control.append(dict(cap=cap,candidate=a,control=b,control_minus_candidate=float(d.mean()),ci95=np.percentile(draws,[2.5,97.5]).tolist(),wins=int((d>0).sum()),ties=int((d==0).sum()),losses=int((d<0).sum())))
    return {"means":qs,"contrasts":control}

def main():
    from concurrent.futures import ProcessPoolExecutor
    sources=json.loads((HERE/"sources.json").read_text())
    RESULTS.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=3) as pool:
        volumes=list(pool.map(volume_run,sources["volumes"]))
    (RESULTS/"servers.json").write_text(json.dumps(volumes,indent=2),encoding="utf8")
    rows=[r for v in volumes for r in v["scores"]]
    (RESULTS/"summary.json").write_text(json.dumps(analyze(rows),indent=2),encoding="utf8")
    print("Done",len(rows),"systems measurements")
if __name__=="__main__":main()

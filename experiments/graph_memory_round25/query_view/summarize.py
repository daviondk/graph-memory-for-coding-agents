"""Cost of exact search after a query changes, including the compact state written once."""
from collections import defaultdict
import numpy as np
from evaluate import METHODS
from make_fixture import D,read,write,sha
def interval(values,groups):
    _,idx=np.unique(groups,return_inverse=True);g=int(idx.max()+1)
    sums=np.bincount(idx,weights=values);count=np.bincount(idx)
    rng=np.random.default_rng(2517);samples=[]
    for _ in range(160):
        take=rng.integers(0,g,(100,g));samples.extend(sums[take].sum(axis=1)/count[take].sum(axis=1))
    return np.quantile(samples,[.00625,.99375]).tolist()
def main():
    lock=read(D/"query-lock.json");assert sha(D/"decisions.json.gz")==lock["decisions"] and sha(D/"times.json.gz")==lock["times"]
    data=read(D/"decisions.json.gz");times=read(D/"times.json.gz");coh=read(D/"cohort.json.gz")
    out={}
    for corpus in ("isetrace","squad"):
        panel=[r for r in data if r["c"]==corpus]
        snapshots={r["key"]:r for r in coh if r["corpus"]==corpus}
        n=len(panel);g=len(snapshots)
        measured=defaultdict(list)
        # One draw per query avoids weighting the timing subsample triple.
        for co,sid,q,rep,m,ns in times:
            if co==corpus and rep==0:measured[m].append(ns)
        base=sum(r["source_bytes"] for r in snapshots.values());summ={}
        for m in METHODS:
            persisted=sum(r["index_bytes"][m] for r in snapshots.values())
            fetched=sum(r["arms"][m][3] for r in panel)
            cells=sum(r["arms"][m][2] for r in panel)
            summ[m]={"mean_source_bytes":fetched/n,"total_source_bytes":fetched,"mean_selects":cells/n,
               "metadata_bytes":persisted,"mean_metadata_bytes":persisted/g,"write_plus_read_bytes":persisted+fetched,
               "mean_write_plus_read_per_query":(persisted+fetched)/n,
               "zero_reads":sum(r["arms"][m][2]==0 for r in panel),
               "exact_window":sum(r["arms"][m][0]==r["ref"] for r in panel),
               "exact_address":sum(r["arms"][m][1]==r["arms"]["scan"][1] for r in panel),
               "median_warm_us":float(np.median(measured[m]))/1000,"p95_warm_us":float(np.quantile(measured[m],.95))/1000}
        comparisons={}
        for m in ("bloom_scan","exact_lazy","bloom_cold"):
            d=[r["arms"]["bloom_lazy"][3]-r["arms"][m][3] for r in panel]
            comparisons[m]={"mean_difference_bytes":float(np.mean(d)),"cluster98_75":interval(d,[r["g"] for r in panel]),
                           "fewer":sum(x<0 for x in d),"more":sum(x>0 for x in d)}
        out[corpus]={"queries":n,"snapshots":g,"common_payload_total":base,"stored_windows":sum(r["windows"] for r in snapshots.values()),
            "queries_per_snapshot":n/g,"summary":summ,"comparisons":comparisons}
    write(D/"results.json",{"results":out,"lock":sha(D/"query-lock.json"),"private_fixture":read(D/"input-lock.json")["private_sqlite"]})
    for c,r in out.items():
        print(c,{k:(int(v["mean_source_bytes"]),int(v["mean_metadata_bytes"]),v["exact_window"],round(v["median_warm_us"],1)) for k,v in r["summary"].items()})
if __name__=="__main__":main()

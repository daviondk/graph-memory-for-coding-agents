from collections import defaultdict
from statistics import median,mean
import math,os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from cfg import *
from bench import METHODS
def ci_ratio(data,cases,ids,state,k,ref,key):
    groups=defaultdict(list)
    for j in ids:
        a=data[state,j,k][key];b=data[state,j,ref][key]
        groups[cases[j]["rid"]].append(math.log(a/b))
    gs=sorted(groups);sums=np.array([sum(groups[t]) for t in gs]);ns=np.array([len(groups[t]) for t in gs])
    rng=np.random.default_rng(26017);boot=[]
    for _ in range(50):
        ix=rng.integers(0,len(gs),(100,len(gs)));boot.extend(np.exp(sums[ix].sum(axis=1)/ns[ix].sum(axis=1)))
    return [float(np.exp(sums.sum()/ns.sum())),*np.quantile(boot,[.025,.975]).tolist()]
def main():
    manifest=load(D/"measurement-seal.json");assert sha_file(D/"measurements.json.gz")==manifest["slices"] and sha_file(D/"interface.json.gz")==manifest["traffic"]
    cases=load(D/"cases.json.gz");c=defaultdict(list);cost={(j,k):[bt,n,h] for j,k,bt,n,h in load(D/"interface.json.gz")}
    times=load(D/"measurements.json.gz")
    for state,r,j,k,body,whole in times:c[state,j,k].append((body,whole))
    assert len(times)==len(cases)*24*len(METHODS)
    data={}
    for k,v in c.items():
        assert len(v)==(21 if k[0]=="warm" else 3)
        data[k]=[median(p[i] for p in v) for i in (0,1)]
    summary={};contrasts={}
    pairs=(("text_pair","text_twice"),("text_pair","text_right"),("text_pair","text_half_right"),("whole_char","text_pair"),("whole_byte","text_pair"),("blob_pair","blob_twice"),("blob_pair","text_pair"),("blob_translated","text_pair"))
    for name in ("all","ise","mdd","squad"):
        ids=[j for j,x in enumerate(cases) if name=="all" or name==x["n"]];tbl={};com={}
        for k in METHODS:
            vals=[cost[j,k] for j in ids]
            tbl[k]={"warm_median_us":median(data["warm",j,k][0] for j in ids)/1000,"fresh_median_us":median(data["fresh",j,k][0] for j in ids)/1000,
                    "fresh_total_median_us":median(data["fresh",j,k][1] for j in ids)/1000,"interface_bytes":mean(v[0] for v in vals),"sql":mean(v[1] for v in vals),"blob_handles":mean(v[2] for v in vals)}
        for k,ref in pairs:
            com[k+"/"+ref]={s:ci_ratio(data,cases,ids,s,k,ref,0) for s in ("warm","fresh")}
            com[k+"/"+ref]["fresh_total"]=ci_ratio(data,cases,ids,"fresh",k,ref,1)
        summary[name]={"n":len(ids),"fields":len({cases[j]["rid"] for j in ids}),"median_field_utf8":median(cases[j]["field_bytes"] for j in ids),"methods":tbl}
        contrasts[name]=com
    p=D/"results.json";out={"seal":sha_file(D/"measurement-seal.json"),"summary":summary,"latency_ratios":contrasts}
    if p.exists():assert load(p)==out
    else:save(p,out)
    print(summary["all"],contrasts["all"])
if __name__=="__main__":main()

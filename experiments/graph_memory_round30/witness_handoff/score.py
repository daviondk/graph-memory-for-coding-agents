"""Evaluate frozen witnesses on actually recorded later read targets and on observed pairs."""
from collections import Counter,defaultdict
from hashlib import sha256
from itertools import chain
from pathlib import Path
import json,struct,sys
import numpy as np
from predict import P,D,ARMS,NULL,get,save
SETS=("future","future_visible","prefix")
SCEN=("no_loss","one_message","one_worker","first_message","shared_source")
def pair(p,lo,hi):return (p,lo[0],lo[1]),(p,hi[0],hi[1])
def load_binary(p):
    seal=get(D/(p+"-forecast-seal.json"));ofs=get(P/(p+"-offsets.json.gz"))
    arr={a:(P/(p+"-"+a+".bin")).read_bytes() for a in seal["arrays"]}
    assert all(sha256(v).hexdigest()==seal["arrays"][a]["sha"] for a,v in arr.items())
    for q,o in ofs.items():
        ix={a:{} for a in list(ARMS)+["full"]};q0=o["start"];f=o["full_start"]
        for j in range(q0,q0+o["n"]):
            key=(arr["keys"][68*j:68*j+32].hex(),struct.unpack_from("<I",arr["keys"],68*j+32)[0],arr["keys"][68*j+36:68*(j+1)].hex())
            for a in ARMS:ix[a][key]=tuple(x for x in struct.unpack_from("<II",arr[a],8*j) if x!=NULL)
            n=struct.unpack_from("<I",arr["full"],f)[0];f+=4
            ix["full"][key]=struct.unpack_from("<"+"I"*n,arr["full"],f);f+=4*n
        yield q,o["events"],ix
def rates(x,y,workers,original):
    n=len(workers);nw=set(workers)
    if not x or not y:return (0.,)*5
    pi=original[0]
    def vulnerable(tags):
        return set(tags) if len(set(tags))==1 else set()
    md=vulnerable(x)|vulnerable(y);wd=vulnerable([workers[i] for i in x])|vulnerable([workers[i] for i in y])
    return (1.,1-len(md)/n,1-len(wd)/len(nw),float(pi not in md),0.)
def main(p):
    seal=get(D/(p+"-projection.json"));assert sha256((P/(p+"-targets.json.gz")).read_bytes()).hexdigest()==seal["target_sha"]
    future={r["id"]:r["future"] for r in get(P/(p+"-targets.json.gz"))};prefix={r["id"]:r["events"] for r in get(P/(p+"-prefix.json.gz"))}
    raw=[];alts=Counter()
    for q,workers,ix in load_binary(p):
        oracle=ix["full"];ev=prefix[q];pref=[v for e in ev for v in ([(s,ls[0],ls[-1]) for s,ls in e["r"] if len(ls)>=2])]
        groups={"future":future[q],"future_visible":[v for v in future[q] if all(key in oracle for key in pair(*v))],"prefix":pref}
        for s in SETS:
            pairs=[pair(*v) for v in groups[s]];methods={};den=len(pairs)
            if not den:continue
            for a,idx in ix.items():
                scores=[]
                for k,l in pairs:scores.append(rates(idx.get(k,()),idx.get(l,()),workers,oracle.get(k,())))
                methods[a]=np.mean(scores,axis=0).tolist()
            if p=="swe":methods["direct_base_snapshot"]=[1.,1.,1.,1.,0.]
            raw.append(dict(id=q,set=s,n=den,arms=methods))
        for k,ids in oracle.items():
            alts["all_keys"]+=1;alts["two_messages"]+=len(ids)>1;alts["two_workers"]+=len({workers[j] for j in ids})>1
    out={};rng=np.random.default_rng(30031)
    for s in SETS:
        panel=[r for r in raw if r["set"]==s]
        if not panel:continue
        n=len(panel);draw=rng.integers(0,n,(10000,n));methods=panel[0]["arms"];mats={a:np.array([r["arms"][a] for r in panel]) for a in methods}
        estimates={a:dict(zip(SCEN,np.mean(v,axis=0).tolist())) for a,v in mats.items()};pairs={}
        for a,b in [("distinct_worker","first_two"),("first_two","one"),("latest","first_two"),("full","distinct_worker")]:
            values=mats[a]-mats[b];ci=np.quantile(values[draw].mean(1),[.025,.975],axis=0).T
            pairs[a+"__"+b]={t:dict(delta=float(values[:,j].mean()),ci=ci[j].tolist(),win=int((values[:,j]>1e-12).sum()),lose=int((values[:,j]<-1e-12).sum())) for j,t in enumerate(SCEN)}
        out[s]=dict(n_cases=n,n_pairs=sum(r["n"] for r in panel),methods=estimates,paired=pairs)
    save(D/(p+"-results.json"),dict(panel=out,alternatives=alts,per_case=save(D/(p+"-per-case.json.gz"),raw)));print(p,[(s,v["n_cases"],v["n_pairs"],v["methods"]["full"]["no_loss"],v["paired"]["distinct_worker__first_two"]["one_worker"],v["paired"]["first_two__one"]["one_message"]) for s,v in out.items()])
if __name__=="__main__":main(sys.argv[1])


"""Construct requests blind to responses, fit on A, seal choices on B, then evaluate B once."""
import base64
import collections
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zlib
from codec import ALL, ARMS, FLAT, contents, predictors, receive, request, serve, whole_frame, tests

D=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(p):return sha(p.read_bytes())
def write(p,data):p.write_text(json.dumps(data,indent=1),encoding="utf8")
def read(p):return json.loads(p.read_bytes())
def archive(p,mode):return gzip.open(p,mode+"t",encoding="utf8",compresslevel=3)
def post(f,r):f.write(json.dumps(r,separators=(",",":"))+"\n")
def rows(p):
    with archive(p,"r") as f:
        for line in f:yield json.loads(line)
def enc(b):return base64.b64encode(b).decode()
def dec(b):return base64.b64decode(b)
def mem(blob,path,vr):
    data=dec(blob)
    assert data[:3]==b"SW3" and len(data)<=4096
    return contents(json.loads(zlib.decompress(data[3:])),path,vr)
def locations(panel,j):
    return list(D/f"{kind}_{panel}_{j}.jsonl.gz" for kind in ("input","answer","requests","packets","metrics"))
def prepare_requests(job):
    panel,j=job;i,_,req,_,_=locations(panel,j)
    n=0
    with archive(req,"w") as out:
        for issue,repo,t,path,vr,blobs in rows(i):
            unique=[];seen={};which={};features={}
            for a in ARMS:
                memory=mem(blobs[a],path,vr);features[a]=predictors(memory,vr);which[a]={}
                for mode in ALL:
                    b=request(path,vr,memory,mode)
                    if b not in seen:seen[b]=len(unique);unique.append(enc(b))
                    which[a][mode]=seen[b]
            post(out,[issue,repo,t,features,which,unique]);n+=1
    return n
def score(job):
    panel,j=job;i,g,req,out,stats=locations(panel,j)
    n=0;exact=0
    with archive(out,"w") as packet,archive(stats,"w") as tab:
        for inp,gold,r in zip(rows(i),rows(g),rows(req),strict=True):
            issue,repo,t,path,vr,blobs=inp
            assert (issue,t)==(gold[0],gold[1])==(r[0],r[2])
            truth={n:s.encode() for n,s in gold[2]};full=whole_frame(truth)
            assert len(truth)>0
            raw=[dec(k) for k in r[-1]];wires=[serve(k,truth,full) for k in raw];unique=[];seen={};index=[];ss={}
            for reply,_ in wires:
                if reply not in seen:seen[reply]=len(unique);unique.append(enc(reply))
                index.append(seen[reply])
            for a in ARMS:
                memory=mem(blobs[a],path,vr);ss[a]={}
                checked=set()
                for name,k in r[-2][a].items():
                    reply,(offered,accepted,lines)=wires[k]
                    if k not in checked:
                        assert receive(raw[k],reply,memory)==truth
                        checked.add(k)
                    exact+=1
                    ss[a][name]=[len(raw[k])+len(reply),len(raw[k]),len(reply),offered,accepted,lines]
            post(packet,[issue,t,unique,index])
            post(tab,[issue,repo,t,r[3],ss,len(truth)]);n+=1
    return [n,exact]
def stats(panel):
    for j in range(8):yield from rows(locations(panel,j)[-1])
def mean(samples):
    return [sum(col)/len(samples) for col in zip(*samples)]
def key(x):return ",".join(map(str,x))
def fit():
    totals=collections.defaultdict(list)
    for iid,repo,t,f,m,nlines in stats("A"):
        ns=m["lru"];diff=[ns[k][0]-ns["full"][0] for k in ALL];feat=f["lru"]
        for length in range(4):totals[key(feat[:length])].append(diff)
    res={}
    for k,samples in sorted(totals.items(),key=lambda p:len(p[0])):
        obs=mean(samples);n=len(samples)
        if k:
            par=res[k.rpartition(",")[0]]["means"]
            obs=[(v*n+16*q)/(n+16) for v,q in zip(obs,par)]
        res[k]={"n":n,"means":obs}
    return res
def choose(model,features,candidates):
    for length in (3,2,1,0):
        node=key(features[:length])
        if node in model:return min(candidates,key=lambda m:model[node]["means"][ALL.index(m)])
def decisions():
    model=fit();write(D/"model.json",model)
    rows_count=0
    with archive(D/"decision_B.jsonl.gz","w") as out:
        for j in range(8):
            for iid,repo,t,f,wires,options in rows(locations("B",j)[2]):
                sel={}
                for a,feat in f.items():
                    sel[a]={"static_flat":choose(model,[],FLAT),"adapt_flat":choose(model,feat,FLAT),
                            "adapt_joint":choose(model,feat,ALL)}
                post(out,[iid,t,sel]);rows_count+=1
    lock=[D/"model.json",D/"decision_B.jsonl.gz",D/"PROTOCOL_RU.md",D/"codec.py",D/"experiment.py",D/"analyze.py",D/"prepare.py",D/"acquire_ranges.py",D/"input_lock.json",D/"request_lock.json"]
    lock.extend(locations("A",j)[-1] for j in range(8))
    write(D/"decision_lock.json",{p.name:digest(p) for p in lock});print("fixed decisions",rows_count)
def main():
    stage=sys.argv[1]
    tests()
    if stage=="request":
        write(D/"input_lock.json",{p.name:digest(p) for panel in ("A","B") for j in range(8) for p in locations(panel,j)[:2]})
        with ProcessPoolExecutor(4) as pool:out=list(pool.map(prepare_requests,[(s,j) for s in ("A","B") for j in range(8)]))
        write(D/"request_lock.json",{locations(panel,j)[2].name:digest(locations(panel,j)[2]) for panel in ("A","B") for j in range(8)})
        print("requests",out)
    elif stage in ("A","B"):
        if stage=="B":
            for p,d in read(D/"decision_lock.json").items():assert digest(D/p)==d
        for lockname in ("input_lock.json","request_lock.json"):
            for p,d in read(D/lockname).items():assert digest(D/p)==d
        with ProcessPoolExecutor(4) as pool:counts=list(pool.map(score,[(stage,j) for j in range(8)]))
        print("exact",stage,counts,flush=True)
    elif stage=="seal":decisions()
if __name__=="__main__":main()

"""Reconstruct each TCP transcript from immutable events without SQLite, sockets or the wire codec."""
from collections import Counter,defaultdict
from hashlib import sha256
from statistics import median
from types import SimpleNamespace
import json
from measure import HERE,ROOT,Hot,SketchPolicy,XOR,prepare,get,put,KEYS


def var(n):
    # Reconstruct unsigned base-128 digits independently of the live serializer.
    assert n>=0
    digits=[n%128]
    while n>=128:
        n//=128;digits.append(n%128)
    return bytes(x+(128 if i+1<len(digits) else 0) for i,x in enumerate(digits))


class Rows(list):
    def fetchone(self):return self[0] if self else None
    def fetchall(self):return self


class Model:
    def __init__(self,src):
        self.src=src;self.stats=Counter();self.tx=sha256();self.rx=sha256()
    def execute(self,stmt,params):
        if len(params)==1 and stmt.startswith("SELECT js "):
            f=params[0];op="posting"
            send=bytes([1])+var(f+1)
            x=self.src.postings.get(f,[])
            rows=[(b"".join(map(var,x)),)] if x else []
        else:
            op="bodies"
            assert stmt.startswith("SELECT members ") and list(params)==sorted(set(params))
            send=bytes([2])+var(len(params))+b"".join(map(var,params))
            rows=[(self.src.events[j],) for j in params]
        receive=bytes([0])+var(len(rows))+b"".join(var(len(v))+v for v, in rows)
        for msg,hasher,f in ((send,self.tx,"req"),(receive,self.rx,"resp")):
            packet=len(msg).to_bytes(4,"big")+msg;hasher.update(packet);self.stats[op+"_"+f+"_bytes"]+=len(packet)
        self.stats[op+"_calls"]+=1
        return Rows(rows)


def rebuild(ops,cap,mode):
    cut=sum(o[0]=="w" for o in ops)//2;cache=None;hot=Hot()
    data=SimpleNamespace(postings=defaultdict(list),events={})
    model=Model(data);proxy=SimpleNamespace(next_id=0,db=model);rows=[]
    for o in ops:
        if cache is None and len(data.events)==cut:
            cache=SketchPolicy(proxy,hot,None if mode=="exact" else XOR,cap)
        if o[0]=="w":
            _,j,_,fs=o
            assert j==len(data.events)
            data.events[j]=b"".join(map(var,fs))
            for f in fs:data.postings[f].append(j)
            proxy.next_id=j+1
            if cache is not None:hot.append(j,fs);cache.after_write(j,fs)
        elif cache is not None:
            _,f,tie,prior,expected=o;b=model.stats.copy()
            pred,count=cache.read(f,tie,prior);assert pred==expected
            diff=model.stats-b
            rows.append([proxy.next_id,f,count["posting_bytes"],count["body_bytes"],*[diff[k] for k in KEYS]])
    return rows,model.tx.hexdigest(),model.rx.hexdigest()


def main():
    raw=get(HERE/"raw.json.gz");streams=get(ROOT/"holdout/events.json.gz");verified=0;projects={}
    for repo,s in streams.items():
        ops,_=prepare(s,"B");summ={}
        for cap in (1024,4096):
            branches={}
            for mode in ("exact","xor"):
                rows,tx,rx=rebuild(ops,cap,mode);branches[mode]=rows
                for rep in range(3):
                    for lag in (0,2):
                        measured=raw[f"{rep}/{repo}/{cap}/{mode}/{lag}"]
                        assert measured["request_sha"]==tx and measured["response_sha"]==rx
                        assert [r[:2]+r[3:] for r in measured["data"]]==rows
                        verified+=len(rows)
            def wire(r):return sum(r[i] for i in (4,5,7,8))
            a,b=branches["exact"],branches["xor"]
            d=[wire(y)-wire(x) for x,y in zip(a,b)]
            summ[cap]=dict(n=len(d),delta=sum(d),query_wins=sum(x<0 for x in d),query_losses=sum(x>0 for x in d),
                           query_ties=d.count(0))
        projects[repo]=summ
    by={}
    for cap in (1024,4096):
        group=[v[cap] for v in projects.values()]
        by[cap]=dict(project_wins=sum(r["delta"]<0 for r in group),project_losses=sum(r["delta"]>0 for r in group),
                     project_ties=sum(r["delta"]==0 for r in group),
                     query_wins=sum(r["query_wins"] for r in group),query_losses=sum(r["query_losses"] for r in group),
                     query_ties=sum(r["query_ties"] for r in group))
    out=dict(verified_queries=verified,runs=len(raw),directions=2*len(raw),projects=projects,groups=by)
    put(HERE/"audit.json",out)
    print(verified,"verified per-query frames",len(raw)*2,"end-to-end byte stream digests",by)


if __name__=="__main__":main()

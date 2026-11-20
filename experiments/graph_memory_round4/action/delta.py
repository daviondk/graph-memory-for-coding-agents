"""Independent strong control matching byte blocks at arbitrary shifted positions using rolling checksums."""
import base64
import collections
import hashlib
import json
import struct
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from codec import Reader, compact, ids, loc, lp, readloc, spans, uint, unpack
from experiment import D,archive,digest,locations,mem,post,read,rows,write

SIZES=(64,256,700)
def canonical(rows):
    groups=spans(rows)
    return loc(groups)+b"".join(lp(rows[n]) for n in ids(groups))
def weak(x):
    a=sum(x)&65535;b=sum((len(x)-i)*v for i,v in enumerate(x))&65535
    return a,b
def strong(x):return hashlib.blake2b(x,digest_size=16).digest()
def input_wire(path,vr,raw,size):
    blocks=[raw[i:i+size] for i in range(0,len(raw),size) if len(raw[i:i+size])>=16]
    first=bytearray(lp(path.encode())+uint(int(vr is not None)))
    if vr is not None:first.extend(uint(vr[0])+uint(vr[1]+1))
    if not blocks:
        first.extend(b"\x00\x00")
        return compact(bytes(first)),[]
    # Separate namespace for rsync codec. Common request path/range and compression.
    first.extend(b"\x02"+uint(size)+uint(len(blocks))+uint(len(blocks[-1])))
    for block in blocks:
        first.extend(struct.pack("<HH",*weak(block)));first.extend(strong(block))
    return compact(bytes(first)),blocks
def signatures(frame):
    r=Reader(unpack(frame));path=r.string()
    if r.num():r.num();r.num()
    tag=r.num()
    if not tag:assert r.num()==0;return {}
    assert tag==2
    size=r.num();num=r.num();last=r.num();by={}
    for i in range(num):
        width=last if i==num-1 else size
        w=struct.unpack("<HH",r.take(4));st=r.take(16)
        table=by.setdefault(width,{});table.setdefault(w,{})[st]=i
    assert r.i==len(r.raw)
    return by
def delta_reply(req,answer,full):
    sig=signatures(req)
    if not sig:return full
    lengths=sorted(sig,reverse=True)
    rolling={};ops=[];j=0;start=0;n=len(answer)
    while j<n:
        found=None
        for width in lengths:
            if j+width>n:continue
            if width not in rolling:rolling[width]=weak(answer[j:j+width])
            candidate=sig[width].get(rolling[width])
            if candidate is not None:
                got=candidate.get(strong(answer[j:j+width]))
                if got is not None:
                    found=(width,got);break
        if found:
            width,idx=found
            if j>start:ops.append(b"l"+lp(answer[start:j]))
            ops.append(b"c"+uint(idx));j+=width;start=j;rolling.clear()
        else:
            for width,(a,b) in list(rolling.items()):
                if j+width>=n:continue
                a=(a-answer[j]+answer[j+width])&65535
                b=(b-width*answer[j]+a)&65535;rolling[width]=(a,b)
            j+=1
    if start<n:ops.append(b"l"+lp(answer[start:]))
    trial=b"R"+compact(uint(len(ops))+b"".join(ops))
    return trial if len(trial)<len(full) else full
def receive(raw,blocks):
    if raw[:1]==b"F":return unpack(raw[1:])
    assert raw[:1]==b"R"
    r=Reader(unpack(raw[1:]));out=bytearray()
    for _ in range(r.num()):
        if r.take(1)==b"l":out.extend(r.string())
        else:out.extend(blocks[r.num()])
    assert r.i==len(r.raw)
    return bytes(out)
def one(job):
    panel,j=job;inputs,answer,_,_,_=locations(panel,j)
    with archive(D/f"delta_{panel}_{j}.jsonl.gz","w") as tab,archive(D/f"delta_wires_{panel}_{j}.jsonl.gz","w") as wires:
        for inp,gold in zip(rows(inputs),rows(answer),strict=True):
            issue,repo,t,path,vr,blobs=inp
            assert (issue,t)==(gold[0],gold[1])
            pri=mem(blobs["lru"],path,vr)
            src=canonical({n:v[0] for n,v in pri.items()});dst=canonical({n:s.encode() for n,s in gold[2]})
            full=b"F"+compact(dst);costs={};raw={}
            for size in SIZES:
                req,blocks=input_wire(path,vr,src,size);reply=delta_reply(req,dst,full)
                assert receive(reply,blocks)==dst
                costs[str(size)]=[len(req)+len(reply),len(req),len(reply)]
                raw[str(size)]=[base64.b64encode(b).decode() for b in [req,reply]]
            post(tab,[issue,repo,t,costs]);post(wires,[issue,t,raw])
def paneldata(panel):
    data={}
    for j in range(8):
        _,_,_,_,metrics=locations(panel,j)
        for s,m in zip(rows(D/f"delta_{panel}_{j}.jsonl.gz"),rows(metrics),strict=True):
            assert s[:3]==m[:3]
            vals={size:q[0] for size,q in s[-1].items()}
            vals["full"]=m[4]["lru"]["full"][0]
            data[s[0],s[2]]=(s[1],vals)
    return data
def tests():
    basis=(b"abacabadabacaba"+b"example data")*220
    for size in SIZES:
        rq,blocks=input_wire("x.py",None,basis,size)
        for dst in [b"insert"+basis[2:]+b"xyz",basis, b"a"]:
            answer=delta_reply(rq,dst,b"F"+compact(dst))
            assert receive(answer,blocks)==dst
def main():
    panel=sys.argv[1];tests()
    if panel=="B":
        for p,v in read(D/"delta_lock.json")["hashes"].items():assert digest(D/p)==v
    with ProcessPoolExecutor(3) as pool:list(pool.map(one,[(panel,j) for j in range(8)]))
    data=paneldata(panel)
    totals={s:sum(v[s] for p,v in data.values()) for s in (*map(str,SIZES),"full")}
    if panel=="A":
        choice=min(totals,key=totals.get);lockfiles=["DELTA_PROTOCOL_RU.md","delta.py","decision_lock.json",*[f"delta_A_{j}.jsonl.gz" for j in range(8)]]
        write(D/"delta_lock.json",dict(choice=choice,totals=totals,hashes={n:digest(D/n) for n in lockfiles}))
    else:
        choice=read(D/"delta_lock.json")["choice"]
        rec={};diff=collections.defaultdict(list)
        metrics={}
        for j in range(8):
            for row in rows(locations(panel,j)[-1]):metrics[row[0],row[2]]=row[4]["lru"]
        for issue,t,policies in rows(D/"decision_B.jsonl.gz"):
            project,vals=data[issue,t]
            k=policies["lru"]["adapt_joint"]
            prop=metrics[issue,t][k][0]
            diff[project].append(vals[choice]-prop)
        import numpy as np
        groups=sorted(diff);ns=np.array([len(diff[g]) for g in groups]);cs=np.array([sum(diff[g]) for g in groups]);ix=np.random.default_rng(184296).integers(len(groups),size=(10000,len(groups)))
        ci=np.quantile(cs[ix].sum(axis=1)/ns[ix].sum(axis=1),[.025,.975])
        write(D/"delta_results.json",dict(fixed_from_A=choice,test_totals=totals,n=len(data),all_wire_checks=len(data)*len(SIZES),
                                         learned_joint_savings=int(sum(cs)),mean=float(sum(cs)/len(data)),cluster95=ci.tolist(),per_project={g:[len(diff[g]),sum(diff[g])] for g in groups}))
    print(panel,totals,choice)
if __name__=="__main__":main()

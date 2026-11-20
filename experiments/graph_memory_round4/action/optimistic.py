"""A whole-response integrity check allows cheap speculative reuse; incorrect copies trigger a charged GET."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

from codec import ALL,FLAT,Reader,compact,ids,loc,lp,predictors,readloc,receive,request,serve,spans,uint,unpack,whole_frame
from experiment import D,archive,choose,dec,digest,enc,locations,mem,post,read,rows,write
from delta import canonical,delta_reply,input_wire,receive as receive_delta

def new_request(path,vr,known):
    if not known:return request(path,vr,{},"full")
    req=bytearray(lp(path.encode())+uint(int(vr is not None)))
    if vr is not None:req.extend(uint(vr[0])+uint(vr[1]+1))
    req.extend(b"\x03"+loc(spans(known)))
    return compact(bytes(req))
def addresses(frame):
    r=Reader(unpack(frame));r.string()
    if r.num():r.num();r.num()
    tag=r.num()
    if tag==0:assert r.num()==0;return set()
    assert tag==3
    result=set(ids(readloc(r)));assert r.i==len(r.raw)
    return result
def strong(b):return hashlib.blake2b(b,digest_size=16).digest()
def answer(frame,current,full,raw):
    held=addresses(frame);used=set(current)&held
    if not used:return full,set()
    geo=spans(current)
    body=loc(geo)+strong(raw)+b"".join(lp(current[n]) for n in ids(geo) if n not in used)
    delta=b"O"+compact(body)
    return (delta,used) if len(delta)<len(full) else (full,set())
def reconstruct(frame,message,memory):
    q=Reader(unpack(message[1:]));geo=readloc(q);held=addresses(frame)
    auth=q.take(16) if message[:1]==b"O" else None
    returned={n:(memory[n][0] if auth is not None and n in held else q.string()) for n in ids(geo)}
    assert q.i==len(q.raw)
    if auth is not None and strong(canonical(returned))!=auth:return None
    return returned
def freeze_plan(job):
    panel,j=job;model=read(D/"model.json")
    with archive(D/f"opt_plan_{panel}_{j}.jsonl.gz","w") as out:
        for issue,repo,t,path,vr,blobs in rows(locations(panel,j)[0]):
            known=mem(blobs["lru"],path,vr);feat=predictors(known,vr)
            selected=[choose(model,feat,FLAT),choose(model,feat,ALL)]
            post(out,[issue,t,selected,enc(new_request(path,vr,known))])
def one(job):
    panel,j=job
    inp,truth,_,_,_=locations(panel,j)
    if read(D/"delta_lock.json")["choice"]!="256":raise ValueError("Frozen identified comparator changed")
    with archive(D/f"opt_raw_{panel}_{j}.jsonl.gz","w") as out,archive(D/f"opt_cost_{panel}_{j}.jsonl.gz","w") as scores:
        for x,y,pl in zip(rows(inp),rows(truth),rows(D/f"opt_plan_{panel}_{j}.jsonl.gz"),strict=True):
            iid,repo,t,path,vr,blobs=x
            assert (iid,t)==(pl[0],pl[1])==(y[0],y[1])
            vals={n:s.encode() for n,s in y[2]};known=mem(blobs["lru"],path,vr);selected=pl[2];opt=dec(pl[3])
            full=whole_frame(vals);raw=canonical(vals);get=request(path,vr,{},"full");msg,used=answer(opt,vals,full,raw)
            actual=reconstruct(opt,msg,known);retry=int(actual is None)
            if retry:actual=reconstruct(get,full,{})
            assert actual==vals
            injected=0
            if used:
                altered=known.copy();n=min(used);altered[n]=(b"INJECTED-CHANGED-LINE"+altered[n][0],altered[n][1])
                # Variable-length deterministic perturbation; on an originally stale map, force all other copied lines true.
                stable={i:(vals[i],0) if i in used else v for i,v in known.items()}
                stable[n]=(b"INJECTED-CHANGED-LINE"+vals[n],0)
                assert reconstruct(opt,msg,stable) is None and reconstruct(get,full,{})==vals
                injected=1
            met={};messages={}
            for label,mode in [("full","full"),("pages","pages"),("adapt_flat",selected[0]),("adapt_joint",selected[1])]:
                normal=request(path,vr,known,mode);reply,_=serve(normal,vals,full)
                assert receive(normal,reply,known)==vals
                messages[label]=[enc(normal),enc(reply)];met[label]=[len(normal)+len(reply),len(normal),len(reply),1]
            prior=canonical({n:v for n,(v,_) in known.items()})
            rq,blocks=input_wire(path,vr,prior,256);rr=delta_reply(rq,raw,full)
            assert receive_delta(rr,blocks)==raw
            messages["rolling256"]=[enc(rq),enc(rr)];met["rolling256"]=[len(rq)+len(rr),len(rq),len(rr),1]
            request_len=len(opt)+retry*len(get);reply_len=len(msg)+retry*len(full)
            messages["optim"]=[enc(opt),enc(msg)]+([enc(get),enc(full)] if retry else [])
            met["optim"]=[request_len+reply_len,request_len,reply_len,1+retry]
            # Content-addressed packets within an action to avoid logging identical literals several times.
            dictionary=[];pool={};indexes={}
            for label,packets in messages.items():
                indexes[label]=[]
                for pkt in packets:
                    if pkt not in pool:pool[pkt]=len(dictionary);dictionary.append(pkt)
                    indexes[label].append(pool[pkt])
            post(out,[iid,t,dictionary,indexes,hashlib.sha256(raw).hexdigest()])
            post(scores,[iid,repo,t,met,len(vals),len(known),len(used),retry,injected,int(msg[:1]==b"O"),len(get)+len(full)])
    return f"{panel}{j}"
def main():
    step=sys.argv[1];jobs=[(p,j) for p in ("A","B","C") for j in range(8)]
    if step=="freeze":
        with ProcessPoolExecutor(4) as pool:list(pool.map(freeze_plan,jobs))
        fs=["OPTIMISTIC_PROTOCOL_RU.md","optimistic.py","opt_stats.py","source_c.py","prepare_c.py","C_counts.json","range_C.json","model.json","delta_lock.json"]
        fs.extend([f"opt_plan_{p}_{j}.jsonl.gz" for p,j in jobs]);fs.extend([locations(p,j)[k].name for p,j in jobs for k in (0,1)])
        write(D/"opt_lock.json",{n:digest(D/n) for n in fs})
    elif step=="score":
        for n,v in read(D/"opt_lock.json").items():assert digest(D/n)==v
        with ProcessPoolExecutor(4) as pool:
            for n in pool.map(one,jobs):print(n,flush=True)
if __name__=="__main__":main()

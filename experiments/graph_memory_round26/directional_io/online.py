"""Token-budgeted local SQL reads using only the source key, boundary anchors and field length."""
from collections import defaultdict
from statistics import median,mean
from time import perf_counter_ns
import random,re,sys,os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from cfg import *
from bench import connect,ONE,TWO,WHOLE
sys.path.insert(0,str(R))
from dataset import c,Tokenizer,TOK
from direction import part
METHODS=("local_pair","local_twice","whole_pair","local_right","whole_right")
def enc(tok,s):return tok.encode(s,add_special_tokens=False)
def clipped(tok,e,a,side,cap,fragment,at_source_edge):
    header=f"[{e}:{a}] ";nh=len(enc(tok,header).ids)
    if side=="R":
        txt=fragment
        if not at_source_edge:
            marks=list(re.finditer(r"\s",txt))
            if not marks:return None
            txt=txt[:marks[-1].start()]
        wire=header+txt;q=enc(tok,wire)
        if len(q.ids)<=cap and not at_source_edge:return None
        end=q.offsets[cap][0] if len(q.ids)>cap else len(wire)
        while len(enc(tok,wire[:end]).ids)>cap:end-=1
        body=wire[len(header):end];l=a;h=a+len(body)
    else:
        txt=fragment
        if not at_source_edge:
            hit=re.search(r"\s",txt)
            if not hit:return None
            txt=txt[hit.end():]
        q=enc(tok,txt);keep=cap-nh
        if len(q.ids)<=keep and not at_source_edge:return None
        start=q.offsets[len(q.ids)-keep][0] if len(q.ids)>keep else 0
        while len(enc(tok,header+txt[start:]).ids)>cap:start+=1
        body=txt[start:];h=a;l=a-len(body)
    return [e,l,h,len(enc(tok,header+body).ids),a,side,nh],header+body
def serve(db,tok,key,method):
    rid,e,left,right,total=key
    targets=[("R",right,256)] if method.endswith("right") else [("L",left,128),("R",right,128)]
    transferred=0;calls=0;resolved={}
    if method.startswith("whole"):
        body=db.execute(WHOLE,(rid,)).fetchone()[0];calls=1;transferred=len(body);text=body.decode()
        for s,a,n in targets:
            op=part(tok,text,e,a,s,n);resolved[s]=(op,f"[{e}:{a}] "+text[op[1]:op[2]])
    else:
        remaining=list(targets);size=2048
        while remaining:
            ranges=[(max(0,a-size),a) if s=="L" else (a,min(total,a+size)) for s,a,cap in remaining]
            if method=="local_pair" and len(ranges)==2:
                (a,b),(c,d)=ranges;parts=db.execute(TWO,(a+1,b-a,c+1,d-c,rid)).fetchone();calls+=1
            else:
                parts=[db.execute(ONE,(a+1,b-a,rid)).fetchone()[0] for a,b in ranges];calls+=len(parts)
            nxt=[]
            for task,(lo,hi),raw in zip(remaining,ranges,parts):
                side,anchor,cap=task;transferred+=len(raw);txt=raw.decode()
                assert len(txt)==hi-lo
                value=clipped(tok,e,anchor,side,cap,txt,lo==0 if side=="L" else hi==total)
                if value:resolved[side]=value
                else:nxt.append(task)
            remaining=nxt;size*=2
    data=[resolved[s] for s,a,b in targets];wire="\n".join(x[1] for x in data)
    assert len(enc(tok,wire).ids)==sum(x[0][3] for x in data)<=256
    return [x[0] for x in data],wire,transferred,calls
def main():
    manifest=load(D/"build.json");assert sha_file(DB)==manifest["db"];src=load(D/"cases.json.gz")
    toks={"ise":Tokenizer.from_file(str(TOK)),"mdd":c.tok(),"squad":Tokenizer.from_file(str(TOK))}
    keys=[]
    for q in src:
        # Service receives no output endpoints, target annotations, or stored byte offsets.
        l,r=q["both"];parse=lambda z:tuple(map(int,z["header"][1:-2].split(":")))
        e,a=parse(l);f,b=parse(r);assert e==f;keys.append((q["rid"],e,a,b,q["field_chars"]))
    db=connect();list(db.execute("select length(body) from field"))
    rng=random.Random(26091);raw=[];counter={}
    for state,rep in (("warm",5),("fresh",1)):
        for i in range(rep):
            ids=list(range(len(src)));rng.shuffle(ids)
            for j in ids:
                r=src[j];names=list(METHODS);rng.shuffle(names)
                for k in names:
                    start=perf_counter_ns();con=connect() if state=="fresh" else db;t0=perf_counter_ns()
                    segments,wire,bt,calls=serve(con,toks[r["n"]],keys[j],k)
                    t1=perf_counter_ns()
                    if state=="fresh":con.close()
                    stop=perf_counter_ns();old=[r["right"]] if k.endswith("right") else r["both"]
                    assert [(x[1],x[2],x[3]) for x in segments]==[(s["l"],s["h"],s["tokens"]) for s in old],(j,k,segments,old)
                    if len(old)==2:assert sha(wire.encode())==r["wire"]
                    else:assert sha(wire[len(old[0]["header"]):].encode())==old[0]["sha"]
                    raw.append([state,i,j,k,t1-t0,stop-start,bt,calls]);counter[j,k]=(bt,calls)
    db.close();digest=save(D/"online-times.json.gz",raw)
    med=defaultdict(list);ranges={}
    for state,i,j,k,ns,total,bt,calls in raw:med[state,j,k].append((ns,total))
    for k,v in med.items():ranges[k]=[median(z[i] for z in v) for i in (0,1)]
    summary={}
    for k in METHODS:
        ids=range(len(src));summary[k]={"warm_us":median(ranges["warm",j,k][0] for j in ids)/1000,"fresh_us":median(ranges["fresh",j,k][0] for j in ids)/1000,"fresh_all_us":median(ranges["fresh",j,k][1] for j in ids)/1000,
            "avg_db_bytes":mean(counter[j,k][0] for j in ids),"avg_calls":mean(counter[j,k][1] for j in ids),"max_calls":max(counter[j,k][1] for j in ids)}
    from results import ci_ratio
    ratio={f"local_pair/{ref}":ci_ratio(ranges,src,list(range(len(src))),"warm","local_pair",ref,0) for ref in ("local_twice","whole_pair","local_right")}
    result={"result":summary,"warm_paired":ratio,"rows":len(raw),"queries":len(src),"raw":digest,"method":sha_file(Path(__file__)),"protocol":sha_file(D/"ONLINE_RU.md"),"db":sha_file(DB)}
    save(D/"online-results.json",result);print(result)
if __name__=="__main__":main()

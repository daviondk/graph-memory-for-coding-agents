"""Source-wire validation and independent sweep for all observed choices and sensitivity pairs."""
from collections import defaultdict,Counter
import sys
from shared25 import *
from dataset import c,ro,Tokenizer,TOK,CACHE,squad_rows
from analyse import targets
def measure(before,after,g):
    endpoints=defaultdict(list)
    for j,seq in enumerate((before,after,g)):
        for e,l,h in seq:
            if h>l:endpoints[e].extend(((l,j,1),(h,j,-1)))
    covered=den=new=0
    for ev in endpoints.values():
        v=[0,0,0];prev=0
        for pos,j,m in sorted(ev):
            n=pos-prev;i,o,z=v
            if z:
                den+=n
                if i or o:covered+=n
            if o and not i:new+=n
            v[j]+=m;prev=pos
    return covered/den,new
def main(name):
    picks=read(D/f"{name}-choices.json.gz");ops=read(D/f"{name}-opened.json.gz");sec=read(D/f"{name}-secondary-cost.json.gz")
    per={z["q"]:z for z in read(D/f"{name}-per-query.json.gz")};g=targets(name,picks)
    tok=c.tok() if name=="mdd" else Tokenizer.from_file(str(TOK));log=Counter();sec_hits=defaultdict(lambda:[0,0])
    def one(q,src):
        r=picks[q];cut=r["cut"];local={}
        def checkop(op):
            spec=tuple(tuple(v) for v in op)
            if spec in local:return local[spec]
            wire=[];spans=[]
            for e,l,h,n,a,side,header in op:
                assert 0<=l<=h<=len(src) and e==cut["e"]
                if side=="L":assert h==a==cut["l"]
                else:assert side=="R" and l==a==cut["h"]
                pre=f"[{e}:{a}] ";physical=pre+src[l:h]
                assert len(tok.encode(pre,add_special_tokens=False).ids)==header
                assert len(tok.encode(physical,add_special_tokens=False).ids)==n
                spans.append((e,l,h));wire.append(physical)
            if len(op)==2:assert [x[5] for x in op]==["L","R"]
            charge=len(tok.encode("\n".join(wire),add_special_tokens=False).ids)
            assert charge==sum(v[3] for v in op)<=256
            candidates=[measure(r["base"],spans,gg) for gg in g[q]];new=candidates[0][1]
            assert all(x[1]==new for x in candidates)
            cov=max(x[0] for x in candidates);log["unique_wire_checks"]+=1
            local[spec]=(int(cov==1),cov,new,charge);return local[spec]
        for k,v in ops[q]["arms"].items():
            got=checkop(v);z=per[q]["arms"][k];assert got==(z["fs"],z["coverage"],z["chars"],z["tokens"])
            log["ordinary"]+=1
        for k,(a,b) in ops[q]["equal"].items():
            for st,op in zip(per[q]["equal"][k],(a,b)):
                assert checkop(op)==(st["fs"],st["coverage"],st["chars"],st["tokens"]);log["primary_matched"]+=1
        for k,(a,b) in sec[q].items():
            x,y=checkop(a),checkop(b);assert x[3]==y[3]
            sec_hits[k][0]+=x[0];sec_hits[k][1]+=y[0];log["additional_matched"]+=2
    if name=="ise":
        conn=ro(R/"read_causes/registry.sqlite");groups=defaultdict(list)
        for q,r in picks.items():groups[r["shard"],r["t"]].append((q,r))
        for (i,t),records in groups.items():
            strings=read(CACHE/f"{i}-{t}.json.gz")["fields"];ids=dict(conn.execute("select e,eid from address where t=?",(t,)))
            for q,r in records:
                cut=r["cut"];one(q,strings[ids[cut["e"]]] if cut else "")
        conn.close()
    else:
        docs={t:txt for t,txt,_ in squad_rows()} if name=="squad" else {i:d[2] for i,d in enumerate(c.get_views()["documents"])}
        for q,r in picks.items():
            cut=r["cut"];one(q,docs[r["t"] if name=="squad" else cut["e"]] if cut else "")
    secondary=read(D/f"{name}-secondary.json")["equal"]
    assert all(x==secondary[k]["hits"] for k,x in sec_hits.items())
    val={"n":len(picks),"counts":dict(log),"results":sha(D/f"{name}-results.json"),"secondary":sha(D/f"{name}-secondary.json")}
    p=D/f"{name}-audit.json"
    if p.exists():assert read(p)==val
    else:save(p,val)
    print(name,val)
if __name__=="__main__":main(sys.argv[1])

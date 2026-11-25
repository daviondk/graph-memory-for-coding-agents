from collections import Counter,defaultdict
from statistics import mean
import sys,unicodedata,hashlib
from rep_io import *
sys.path.insert(0,str(R))
from dataset import Tokenizer,TOK
def canon(v):return " ".join(unicodedata.normalize("NFKC",v).casefold().split())
def joined(a):return "\n\n".join(p["context"] for p in a["paragraphs"])
def getids(a):return [(q["id"],canon(q["question"])) for p in a["paragraphs"] for q in p["qas"]]
def complete(ranges,gold):
    vals=[]
    for lo,hi in gold:
        last=lo;credit=0
        for lower,upper in sorted(ranges):
            l,h=max(last,lo,lower),min(hi,upper)
            if l<h:credit+=h-l;last=h
        vals.append(credit/(hi-lo))
    return max(vals)
def main():
    freeze();co=read(D/"cohort.json.gz");chosen=co["panel"];tok=Tokenizer.from_file(str(TOK));res=read(D/"results.json");special=read(D/"strong-results.json")
    dev=read(DEV)["data"];train=read(TRAIN)["data"];oldq={i for a in dev for i,x in getids(a)};oldword={x for a in dev for i,x in getids(a)}
    present=set();wordset=set();raw_by={};gold={};article=set();body_norm=set();paragraph=set()
    def forms(a):
        return canon(a["title"].replace("_"," ")),hashlib.sha256(canon(joined(a)).encode()).digest(),{hashlib.sha256(x.encode()).digest() for p in a["paragraphs"] if len(x:=canon(p["context"]))>=128}
    for a in dev:
        t,b,ps=forms(a);article.add(t);body_norm.add(b);paragraph.update(ps)
    for a in train:
        t=a["title"]
        if t not in chosen:continue
        name,b,ps=forms(a);assert name not in article and b not in body_norm and not(paragraph&ps);article.add(name);body_norm.add(b);paragraph.update(ps)
        raw_by[t]=joined(a);ids=set(chosen[t]["ids"]);off=0
        for p in a["paragraphs"]:
            for row in p["qas"]:
                i=row["id"]
                if i not in ids:continue
                q=canon(row["question"]);assert i not in present|oldq and q not in wordset|oldword;present.add(i);wordset.add(q)
                targets=[]
                for ans in row["answers"]:
                    l=ans["answer_start"];h=l+len(ans["text"])
                    if h>l and 0<=l and h<=len(p["context"]) and p["context"][l:h]==ans["text"]:targets.append((off+l,off+h))
                gold[i]=set(targets)
            off+=len(p["context"])+2
    saved={r["q"]:r for r in read(D/"per-query.json.gz")};strong={r["q"]:r for r in read(D/"strong-outcomes.json.gz")}
    paid=checks=unique=0;traces=defaultdict(Counter)
    for i in range(8):
        choices=read(D/f"choices-{i}.json.gz");opens=read(D/f"read-{i}.json.gz");extra=read(D/f"strong-{i}.json.gz")
        for q,r in choices.items():
            if not gold[q]:continue
            src=raw_by[r["t"]];base=[(l,h) for e,l,h in r["base"]];cache={}
            def verify_wire(z,v):
                nonlocal checks,unique
                key=tuple(tuple(s) for s in z)
                if key not in cache:
                    parts=[]
                    for e,l,h,nt,anchor,side,header in z:
                        head=f"[{e}:{anchor}] ";assert len(tok.encode(head,add_special_tokens=False).ids)==header
                        wire=head+src[l:h];assert len(tok.encode(wire,add_special_tokens=False).ids)==nt<=256;parts.append(wire)
                    bill=len(tok.encode("\n".join(parts),add_special_tokens=False).ids);assert bill==sum(seg[3] for seg in z)
                    cov=complete(base+[(s[1],s[2]) for s in z],gold[q]);cache[key]=[int(cov==1),cov,bill,len(z),sum(s[6] for s in z)];unique+=1
                assert cache[key]==v;checks+=1
            zz=saved[q];actual=opens[q]
            for k,op in actual["arms"].items():verify_wire(op,zz["vals"][k])
            for k,pair in actual["equal"].items():
                for op,vals in zip(pair,zz["eq"][k]):verify_wire(op,vals)
                assert zz["eq"][k][0][2]==zz["eq"][k][1][2];paid+=1
            for op,k in zip(extra[q],("a","b")):verify_wire(op,strong[q][k])
            assert strong[q]["a"][2]==strong[q]["b"][2];paid+=1
            x,y=zz["eq"]["both-right"];traces[r["t"]]["delta"]+=x[0]-y[0]
    assert set(saved)==set(strong)==present and len(traces)==res["selected_articles"] and sum(z["delta"] for z in traces.values())==res["primary"]["net"]
    out={"queries":len(present),"articles":len(traces),"ordinary_and_paired_audit":checks,"unique_wire":unique,"equal_question_pair_costs":paid,"gold_positions":sum(map(len,gold.values())),"cohort":sha(D/"cohort.json.gz"),"results":sha(D/"results.json"),"strong":sha(D/"strong-results.json")}
    f=D/"verified.json"
    if f.exists():assert read(f)==out
    else:save(f,out)
    print(out)
if __name__=="__main__":main()

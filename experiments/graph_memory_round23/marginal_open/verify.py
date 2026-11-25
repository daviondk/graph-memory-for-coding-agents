"""Independent sweep-line check from public coordinates, registry and gold. Run after score.py."""
from collections import defaultdict, Counter
from fractions import Fraction
from math import comb
import sqlite3
from common import D,W,PARENT,sha,read,save,check_plan

ARMS=("first","bm25","first_positive","max_novelty","rank_novelty")
PAIRS=(("rank_novelty","bm25"),("rank_novelty","first_positive"),("first_positive","bm25"))

def counts(visible,opened,gold):
    events=defaultdict(list)
    for tag,ranges in enumerate((visible,opened,gold)):
        for e,l,h in ranges:
            if l<h:events[e].extend(((l,tag,1),(h,tag,-1)))
    totals=Counter()
    for seq in events.values():
        v=[0,0,0];prev=0
        for p,tag,sign in sorted(seq):
            n=p-prev;i,o,g=v
            if g:totals["g"]+=n
            if o:totals["o"]+=n
            if o and not i:totals["new"]+=n
            if g and i:totals["old_gold"]+=n
            if g and o:totals["open_gold"]+=n
            if g and o and not i:totals["new_gold"]+=n
            v[tag]+=sign;prev=p
        assert v==[0,0,0]
    return totals

def ids(reg,t):
    return {(eid,ptr):e for e,eid,ptr in reg.execute("select e,eid,ptr from address where t=?",(t,))}
def gold_ranges(g,lookup):
    return [(lookup[x["event_id"],x["json_pointer"]],x["char_start"],x["char_end"]) for x in g]
def db(path):
    return sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True)

def main():
    check_plan();res=read(D/"results.json");pred=read(D/"choice-seal.json");actions=read(D/"opened-seal.json");individual=read(D/"per-query.json.gz")
    assert res["individual"]==sha(D/"per-query.json.gz") and res["actions"]==sha(D/"opened-seal.json")
    assert pred["visible"]==sha(D/"visible-seal.json") and actions["choice"]==sha(D/"choice-seal.json")
    gold=read(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    reg=db(PARENT/"registry.sqlite");cat=db(D/"field-lengths.sqlite");assert cat.execute("pragma integrity_check").fetchone()[0]=="ok"
    audited=0;sumall=defaultdict(Counter);cldiff=defaultdict(Counter);seen=set();cl=set()
    for i in range(8):
        name,h,n=pred["parts"][i];assert sha(D/name)==h;choices={r["q"]:r for r in read(D/name)}
        name,h,n=actions["files"][i];assert sha(D/name)==h;executed={r["q"]:r["open"] for r in read(D/name)}
        for rec in read(PARENT/f"receipts-{i}.json.gz"):
            q,t=rec["q"],rec["t"];assert q not in seen;seen.add(q);cl.add(t)
            paid,_,visible,wire=rec["arms"]["ratio/merged"]["paid"]["2048"]
            observed=individual[q]["arms"];p=choices.pop(q);out=executed.pop(q);assert p["wire"]==wire and p["paid_in"]==paid<=2048
            gs=gold_ranges(gold[q],ids(reg,t));fs={}
            for k in ARMS:
                op=out[k];a=p["picks"][k];assert (a is None)==(op is None)
                if a:
                    e,l,h,nwp,rank,end,unseen,width=a
                    assert width==end-l and unseen==counts(visible,[(e,l,end)],[])["new"]
                    limit=cat.execute("select n from field_size where t=? and e=?",(t,e)).fetchone()[0]
                    assert any(f==e and x<=l<y for f,x,y in visible)
                    assert 0<=l<=h<=limit and l<=end<=limit and op[:2]==[e,l] and op[2]<=limit
                    assert 0<op[3]<=256 and (unseen>0 or k in ("first","bm25"))
                else:assert k in ("first_positive","rank_novelty","max_novelty") and p["eligible_windows"]==0
                z=counts(visible,[op[:3]] if op else [],gs);g=z["g"]
                o=observed[k];assert g>0
                full=int(z["old_gold"]+z["new_gold"]==g);fs[k]=full
                assert (full,z["new"],z["new_gold"],z["o"],int(z["open_gold"]==g),int(z["old_gold"]==g))==(o["union_fs"],o["added_source_chars"],o["gold_gain_chars"],o["returned_source_chars"],o["open_only_fs"],o["initial_fs"])
                assert (z["old_gold"]+z["new_gold"])/g==o["union_coverage"] and o["open_tokens"]==(op[3] if op else 0)
                sumall[k].update(hits=full,tokens=o["open_tokens"],null=int(op is None),issued_zero=int(op is not None and z["new"]==0))
                audited+=1
            for x,y in PAIRS:cldiff[x+"-"+y][t]+=fs[x]-fs[y]
        assert not choices and not executed
    for k,c in sumall.items():
        s=res["summary"][k];assert [c["hits"],c["tokens"]/len(seen),c["null"],c["issued_zero"]]==[s["hits"],s["open_tokens"],s["abstained"],s["issued_zero_new"]]
    sparse={}
    for key,each in cldiff.items():
        vals=[a for a in each.values() if a];n=len(vals);m=abs(sum(vals));assert n<=18
        totals=Counter({0:1})
        for v in vals:
            nxt=Counter()
            for x,mult in totals.items():nxt[x+abs(v)]+=mult;nxt[x-abs(v)]+=mult
            totals=nxt
        sparse[key]={"nonzero_clusters":n,"net":sum(vals),"exact_two_sided_cluster_sign_flip_p":sum(freq for d,freq in totals.items() if abs(d)>=m)/2**n}
    assert seen==set(individual)==set(gold) and len(cl)==1207 and audited==10000
    reg.close();cat.close()
    val={"n":len(seen),"clusters":len(cl),"decisions_checked":audited,"results":sha(D/"results.json"),"sparse_sensitivity":sparse}
    if (D/"verification.json").exists():assert read(D/"verification.json")==val
    else:save(D/"verification.json",val)
    print(val)
if __name__=="__main__":main()

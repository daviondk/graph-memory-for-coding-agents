"""Equal realized token cost after fixed choices. Source and gold are accessed in separate phases."""
from collections import defaultdict
from tokenizers import Tokenizer
from common import *
from prepare import CACHE
from verify import db,counts,ids,gold_ranges,PAIRS
def clip(tok,action,body,cap):
    if action is None or cap<=0:return None
    e,l,h,n=action;head=f"[{e}:{l}] ";s=head+body[l:h]
    if n<=cap:return action
    enc=tok.encode(s,add_special_tokens=False);assert len(enc.ids)==n
    end=enc.offsets[cap][0]
    while end>=len(head):
        cost=len(tok.encode(s[:end],add_special_tokens=False).ids)
        if cost<=cap:return [e,l,l+end-len(head),cost]
        end-=1
    return None

def make_actions():
    seal=read(D/"opened-seal.json");reg=db(PARENT/"registry.sqlite");tok=Tokenizer.from_file(str(TOK))
    rows={}
    for i,(name,h,n) in enumerate(seal["files"]):
        assert sha(D/name)==h
        grouped=defaultdict(list)
        for r in read(D/name):grouped[r["t"]].append(r)
        for t,records in grouped.items():
            src=read(CACHE/f"{i}-{t}.json.gz")["fields"];lookup=dict(reg.execute("select e,eid from address where t=?",(t,)))
            for r in records:
                vals={}
                for x,y in PAIRS:
                    a,b=r["open"][x],r["open"][y];cap=min(a[3],b[3]) if a and b else 0
                    while cap:
                        p=clip(tok,a,src[lookup[a[0]]],cap);q=clip(tok,b,src[lookup[b[0]]],cap)
                        c,d=(p[3] if p else 0),(q[3] if q else 0)
                        if c==d:break
                        assert min(c,d)<cap;cap=min(c,d)
                    if not cap:p=q=None
                    vals[x+"-"+y]=[p,q]
                rows[r["q"]]=vals
    reg.close();save(D/"cost-actions.json.gz",rows);save(D/"cost-seal.json",{"actions":sha(D/"cost-actions.json.gz"),"parent":sha(D/"opened-seal.json"),"plan":sha(D/"COST_CONTROL_RU.md"),"script":sha(Path(__file__))})

def evaluate():
    seal=read(D/"cost-seal.json");assert seal["actions"]==sha(D/"cost-actions.json.gz") and seal["plan"]==sha(D/"COST_CONTROL_RU.md")
    rows=read(D/"cost-actions.json.gz");reg=db(PARENT/"registry.sqlite")
    gold=read(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz");sums={}
    for i in range(8):
        for rec in read(PARENT/f"receipts-{i}.json.gz"):
            q,t=rec["q"],rec["t"];gs=gold_ranges(gold[q],ids(reg,t));visible=rec["arms"]["ratio/merged"]["paid"]["2048"][2]
            for key,(a,b) in rows.pop(q).items():
                tokens=(a[3] if a else 0,b[3] if b else 0);assert tokens[0]==tokens[1]<=256
                zz=[counts(visible,[op[:3]] if op else [],gs) for op in (a,b)]
                u,v=(int(z["old_gold"]+z["new_gold"]==z["g"]) for z in zz)
                s=sums.setdefault(key,dict(n=0,hits=[0,0],wins=0,losses=0,tokens=0,both_zero=0));s["n"]+=1;s["hits"][0]+=u;s["hits"][1]+=v
                s["wins"]+=u>v;s["losses"]+=v>u;s["tokens"]+=tokens[0];s["both_zero"]+=tokens[0]==0
    assert not rows and all(s["n"]==2000 for s in sums.values())
    for s in sums.values():s["average_real_tokens"]=s["tokens"]/s["n"]
    save(D/"cost-results.json",{"actions":seal["actions"],"pairs":sums});print(sums)
if __name__=="__main__":
    if not (D/"cost-seal.json").exists():make_actions()
    evaluate()

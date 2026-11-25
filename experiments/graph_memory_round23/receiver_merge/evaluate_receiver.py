"""Compare receiver reconstruction with reconstruction before transmission."""
from collections import defaultdict
import sqlite3
import numpy as np
from receive import D,SOURCE,read,sha,write
from score import measure,contrasts

def main():
    lock=read(D/"receiver-lock.json")
    assert lock["protocol"]==sha(D/"PROTOCOL_RU.md") and lock["code"]==sha(D/"receive.py") and lock["source"]==sha(SOURCE/"receipt-lock.json")
    orig=read(SOURCE/"per-query.json.gz")["questions"]
    action=read(D.parent/"address_open/per-query.json.gz")["rows"]
    gold=read(D.parents[1]/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    book=defaultdict(dict)
    for t,e,eid,ptr in db.execute("select t,e,eid,ptr from address"):book[t][eid,ptr]=e
    db.close();rows={}
    for f,h in sorted(lock["files"].items()):
        assert sha(D/f)==h
        for q,r in read(D/f).items():
            assert q not in rows
            t=r["t"]; ref=[(book[t][v["event_id"],v["json_pointer"]],v["char_start"],v["char_end"]) for v in gold[q]]
            m,state=measure(ref,r["shown"]);e,l,h,n=r["opened"];a,_=measure(ref,[(e,l,h)] if l<h else [])
            assert m[0]==m[1] and 0<=r["tokens_internal"]<=2048
            old=orig[q]["values"]["ratio/short/2048"];merged=orig[q]["values"]["ratio/merged/2048"];chosen=action[q]["outcomes"]["ratio/merged/bm25"]
            if r["raw"]<=2048:
                assert m[0]==old[0] and abs(m[2]-old[2])<1e-12
            assert m[0]<=old[0] and m[2]<=old[2]+1e-12 and r["tokens_in"]==old[3]
            rows[q]={"t":t,"values":{"sender":[merged[0],merged[1],merged[2]],"receiver":m,
              "sender_read":[chosen[0],chosen[1],chosen[2]],"receiver_read":[a[0],int(e>=0 and any(g[0]==e for g in ref)),a[2]]},
              "cost":[r["tokens_in"],r["raw"],r["tokens_internal"],merged[3],n,chosen[3]]}
    assert set(rows)==set(orig)==set(gold)
    ordered=[rows[q] for q in sorted(rows)];vals=[r["values"] for r in ordered]
    stats=contrasts(vals,[r["t"] for r in ordered],[("sender","receiver",0),("sender_read","receiver_read",0)])
    sums={k:np.mean([v[k] for v in vals],axis=0).tolist() for k in vals[0]}
    hits={k:int(sum(v[k][0] for v in vals)) for k in vals[0]}
    costs=np.array([r["cost"] for r in ordered])
    write(D/"per-query.json.gz",{"rows":rows,"source_columns":["full_support","intact","coverage"],"read_columns":["full_support","any_field","coverage"],
           "cost_columns":["receiver_wire","receiver_internal_raw","receiver_internal_paid","sender_wire","receiver_open","sender_open"]})
    write(D/"results.json",{"q":len(rows),"t":len(book),"read_lock":sha(D/"receiver-lock.json"),"outcomes_sha":sha(D/"per-query.json.gz"),
       "primary":stats,"means":sums,"hits":hits,"cost_means":costs.mean(axis=0).tolist(),"receiver_internal_trims":int(sum(costs[:,1]>2048))})
    print(stats,sums,costs.mean(axis=0))
if __name__=="__main__":main()

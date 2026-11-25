"""Score sealed one-read choices in the benchmark's original character space."""
from collections import defaultdict
import sqlite3
import numpy as np
from choose import D,SOURCE,read,sha,write
from score import measure

def main():
    lock=read(D/"read-lock.json")
    assert sha(D/"PROTOCOL_RU.md")==lock["protocol"] and sha(D/"choose.py")==lock["code"] and sha(SOURCE/"receipt-lock.json")==lock["source"]
    off=D.parents[1]/"graph_memory_round18/isetrace_official"
    gold=read(off/"gold-spans.json.gz"); modes={r["query_id"]:r["memory_mode"] for r in read(off/"cohort.json")}
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    addresses=defaultdict(dict)
    for t,e,eid,ptr in db.execute("SELECT t,e,eid,ptr FROM address"):
        addresses[t][eid,ptr]=e
    db.close()
    rows={}
    for f,h in sorted(lock["files"].items()):
        assert sha(D/f)==h
        for q,row in read(D/f).items():
            assert q not in rows
            t=row["t"]
            truth=[(addresses[t].get((v["event_id"],v["json_pointer"]),-1),v["char_start"],v["char_end"]) for v in gold[q]]
            fields={(v["event_id"],v["json_pointer"]) for v in gold[q]}
            options={}
            for arm,(e,l,h,tok) in row["read"].items():
                assert tok<=256
                m,_=measure(truth,[(e,l,h)] if l<h else [])
                options[arm]=[m[0],int(e>=0 and any(g[0]==e for g in truth)),m[2],tok]
            rows[q]={"t":t,"one_field":len(fields)==1,"mode":modes[q],"outcomes":options}
    assert set(rows)==set(gold) and len(rows)==2000
    keys=sorted(next(iter(rows.values()))["outcomes"])
    def summary(group):
        result={}
        for arm in keys:
            a=np.array([r["outcomes"][arm] for r in group])
            result[arm]={"n":len(a),"hits":int(a[:,0].sum()),"fields":int(a[:,1].sum()),"coverage":a[:,2].mean(),"tokens":a[:,3].mean()}
        return result
    ordered=[rows[q] for q in sorted(rows)]
    left="ratio/merged/bm25";right="ratio/short/bm25"
    a=np.array([r["outcomes"][left][0]-r["outcomes"][right][0] for r in ordered])
    labels,idx=np.unique([r["t"] for r in ordered],return_inverse=True);g=len(labels)
    sums=np.bincount(idx,weights=a); counts=np.bincount(idx); stats=[]
    rng=np.random.default_rng(2302)
    for _ in range(100):
        ids=rng.integers(g,size=(100,g));stats.extend(sums[ids].sum(axis=1)/counts[ids].sum(axis=1))
    write(D/"per-query.json.gz",{"columns":["full_support","any_field","coverage","tokens"],"rows":rows})
    write(D/"results.json",{"gold":sha(off/"gold-spans.json.gz"),"read_lock":sha(D/"read-lock.json"),
      "per_query":sha(D/"per-query.json.gz"),"all":summary(ordered),"one_field":summary([r for r in ordered if r["one_field"]]),
      "by_mode":{m:summary([r for r in ordered if r["mode"]==m]) for m in sorted(set(modes.values()))},
      "primary":{"left":left,"right":right,"delta":a.mean(),"wins":int(sum(a>0)),"losses":int(sum(a<0)),"cluster95":np.quantile(stats,[.025,.975]).tolist(),"clusters":g}})
    print(read(D/"results.json")["primary"])
if __name__=="__main__":main()

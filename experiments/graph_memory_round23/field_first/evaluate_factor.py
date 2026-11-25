"""Score the two-by-two field and position choices after predictions are sealed."""
from collections import defaultdict
import sqlite3
import numpy as np
from decide import D,PARENT,SOURCE,read,sha,write
from score import measure,contrasts

def main():
    lock=read(D/"read-lock.json")
    assert lock["protocol"]==sha(D/"PROTOCOL_RU.md") and lock["code"]==sha(D/"decide.py")
    assert lock["controls"]==sha(PARENT/"read-lock.json") and lock["source"]==sha(SOURCE/"receipt-lock.json")
    gold=read(D.parents[1]/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    book=defaultdict(dict)
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    for t,e,eid,ptr in db.execute("select t,e,eid,ptr from address"):book[t][eid,ptr]=e
    db.close(); rows={}; total=defaultdict(list); changes=defaultdict(int)
    for f,h in sorted(lock["files"].items()):
        assert sha(D/f)==h
        for q,r in read(D/f).items():
            t=r["t"];ref=[(book[t][v["event_id"],v["json_pointer"]],v["char_start"],v["char_end"]) for v in gold[q]]
            row={}
            for k,(e,l,h,tok) in r["read"].items():
                m,_=measure(ref,[(e,l,h)] if l<h else [])
                v=[m[0],int(any(g[0]==e for g in ref)),m[2],tok]
                row[k]=v;total[k].append(v)
            for a in ("ratio/merged","ratio/short","skip/merged","skip/short"):
                for u,v in (("anchor/lex","anchor/first"),("anchor/first","lex/first"),("lex/lex","lex/first")):
                    changes[f"{a} {u} vs {v}"]+=int(r["read"][a+"/"+u][:2]!=r["read"][a+"/"+v][:2])
            assert q not in rows;rows[q]={"t":t,"values":row}
    assert set(rows)==set(gold)
    baseline=read(PARENT/"per-query.json.gz")["rows"]
    for q,r in rows.items():
        for k,v in r["values"].items():
            arm="/".join(k.split("/")[:-2]);tag="/".join(k.split("/")[-2:])
            if tag in ("anchor/first","lex/lex"): assert baseline[q]["outcomes"][arm+("/first" if tag=="anchor/first" else "/bm25")]==v
    ordrows=[rows[q] for q in sorted(rows)]
    pairs=[("ratio/merged/anchor/lex","ratio/merged/anchor/first",0),("ratio/merged/anchor/first","ratio/merged/lex/first",0)]
    stats=contrasts([r["values"] for r in ordrows],[r["t"] for r in ordrows],pairs)
    summaries={}
    for k,v in total.items():
        a=np.array(v);summaries[k]={"hits":int(a[:,0].sum()),"fields":int(a[:,1].sum()),"coverage":a[:,2].mean(),"tokens":a[:,3].mean()}
    write(D/"per-query.json.gz",{"columns":["full_support","any_field","coverage","tokens"],"rows":rows})
    write(D/"results.json",{"q":len(rows),"t":len(set(r["t"] for r in ordrows)),"matched_old":len(rows)*8,
      "per_query":sha(D/"per-query.json.gz"),"read_lock":sha(D/"read-lock.json"),"summaries":summaries,"changes":changes,"primary":stats})
    print(stats)
if __name__=="__main__":main()

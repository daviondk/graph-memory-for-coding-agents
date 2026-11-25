"""Score the frozen addresses, verifying all original decisions and the containment bound."""
from collections import defaultdict,Counter
import sqlite3
import numpy as np
from extend import D,UP,SOURCE,read,sha,write
from score import measure,contrasts
def main():
    lock=read(D/"extend-lock.json")
    assert lock["source"]==sha(UP/"read-lock.json") and lock["protocol"]==sha(D/"PROTOCOL_RU.md") and lock["code"]==sha(D/"extend.py")
    gold=read(D.parents[1]/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    control=read(UP/"per-query.json.gz")["rows"]
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    book=defaultdict(dict)
    for t,e,eid,ptr in db.execute("select t,e,eid,ptr from address"):book[t][eid,ptr]=e
    db.close();rows={};total=defaultdict(list);counts=Counter()
    for f,digest in sorted(lock["files"].items()):
        assert sha(D/f)==digest
        for q,row in read(D/f).items():
            t=row["t"];ref=[(book[t][g["event_id"],g["json_pointer"]],g["char_start"],g["char_end"]) for g in gold[q]]
            v={}
            for arm,(old,new,offered) in row["arms"].items():
                for suffix,(e,l,h,n) in (("old",old),("new",new)):
                    m,_=measure(ref,[(e,l,h)] if h>l else [])
                    cell=[m[0],m[2],n];v[arm+"/"+suffix]=cell;total[arm+"/"+suffix].append(cell)
                orig=control[q]["values"]["ratio/merged/anchor/"+arm]
                assert [orig[0],orig[2],orig[3]]==v[arm+"/old"]
                assert v[arm+"/old"][0]<=v[arm+"/new"][0] and v[arm+"/old"][1]<=v[arm+"/new"][1]
                counts[arm+"_eligible"]+=int(offered);counts[arm+"_extended"]+=int(new[1]<old[1])
                v[arm+"/gain"]=[v[arm+"/new"][0]-v[arm+"/old"][0]]
            assert q not in rows;rows[q]={"t":t,"values":v}
    assert set(rows)==set(gold); ordered=[rows[q] for q in sorted(rows)]
    stats=contrasts([r["values"] for r in ordered],[r["t"] for r in ordered],[("lex/new","first/new",0),("lex/gain","first/gain",0)])
    summary={k:{"hits":int(np.sum(np.array(v)[:,0])),"coverage":np.mean(np.array(v)[:,1]),"tokens":np.mean(np.array(v)[:,2])} for k,v in total.items()}
    write(D/"per-query.json.gz",{"rows":rows,"columns":["full_support","coverage","tokens"]})
    write(D/"results.json",{"primary":stats,"counts":counts,"summaries":summary,"q":len(rows),"t":len(book),"outcomes":sha(D/"per-query.json.gz"),"seal":sha(D/"extend-lock.json")})
    print(stats,counts,summary)
if __name__=="__main__":main()

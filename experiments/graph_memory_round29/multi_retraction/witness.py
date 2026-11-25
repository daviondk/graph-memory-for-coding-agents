"""Enumerate the best candidate contained in each source span, independently of Fenwick pruning."""
import hashlib
from pathlib import Path
import sqlite3
import numpy as np
from store import state
from multiban_design import D,arrays,read,save,sha

def main():
    p,_,old,_,base=state();db=sqlite3.connect(old/"full.sqlite");compact=sqlite3.connect(base/"pareto.sqlite")
    rows={}
    for ix,q in enumerate(p["qids"]):
        score,order,l,h=arrays(db,ix);n=len(order);sorting=np.argsort(-l,kind="stable");starts=l[sorting]
        coord,hi=np.unique(h,return_inverse=True);active=np.full(len(coord),n,dtype=np.int32);wins=np.empty(n,np.int32)
        marks=np.flatnonzero(np.r_[True,starts[1:]!=starts[:-1],True])
        for b,e in zip(marks[:-1],marks[1:]):
            ids=sorting[b:e];np.minimum.at(active,hi[ids],ids)
            prefix=np.minimum.accumulate(active);wins[ids]=prefix[hi[ids]]
        # Rank is a strict total order. Lower rank implies a better, fully nested answer.
        ranks=np.arange(n);assert np.all((l[wins]>=l)&(h[wins]<=h)&(wins<=ranks)&(wins[wins]==wins))
        live=order[wins==ranks]
        actual=np.asarray([r[0] for r in compact.execute("SELECT ord FROM r WHERE q=? ORDER BY score DESC,ord",(ix,))])
        assert np.array_equal(live,actual)
        rows[q]={"candidates":n,"self_winners":len(live),"strictly_dominated":n-len(live),
                 "witness_hash":hashlib.sha256(order[wins].astype("<i4").tobytes()).hexdigest()}
    db.close();compact.close();save(D/"witnesses.json.gz",rows)
    save(D/"witness-seal.json",{"input":sha(D/"build-seal.json"),"code":sha(Path(__file__)),"rows":sha(D/"witnesses.json.gz"),
        "all":sum(r["candidates"] for r in rows.values()),"self":sum(r["self_winners"] for r in rows.values()),"dominated":sum(r["strictly_dominated"] for r in rows.values())})
if __name__=="__main__":main()

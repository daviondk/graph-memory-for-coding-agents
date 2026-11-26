"""Recompute aggregate costs from decision traces and estimate paired uncertainty by title."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent

def read(path):
    data=(ROOT/path).read_bytes()
    return json.loads(gzip.decompress(data) if str(path).endswith(".gz") else data)

def put(path, record):
    (ROOT/path).write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf8")

def interval(events,order,reference,candidate):
    names=sorted({e[1] for e in events})
    index={v:i for i,v in enumerate(names)}
    summary=np.zeros((len(names),2))
    for j,(r,c) in enumerate(zip(reference,candidate)):
        group=index[events[order[j]][1]]
        summary[group]+=(r[0]-c[0],1)
    rng=np.random.default_rng(32071)
    result=[]
    for _ in range(100):
        boot=summary[rng.integers(len(names),size=(100,len(names)))].sum(axis=1)
        result.extend(100*boot[:,0]/boot[:,1])
    return np.quantile(result,[.025,.975]).tolist()

def main():
    rows=read("events.json.gz");tables=read("results.json")
    revision_count=Counter();rev_sets={};all_titles=set()
    for _,title,rev,*_ in rows:
        rev_sets.setdefault(title,set()).add(rev)
    output={}
    for name in ("file","hash"):
        order=list(range(len(rows)))
        if name=="hash":
            order.sort(key=lambda i:sha256(rows[i][0].encode()).digest())
        changed,prior=set(),{}
        for j,i in enumerate(order):
            _,title,rev,*_=rows[i]
            if title in prior and prior[title]!=rev:changed.add(j)
            prior[title]=rev
        for mode,arms in tables["arms"][name].items():
            for k,summary in arms.items():
                trace=read(f"{name}-{mode}-{k}.json.gz")
                assert len(trace)==len(rows) and all(m in (0,1) for m,_ in trace)
                assert sum(m for m,_ in trace)==summary["reads"]
                assert sum(m*rows[i][3] for i,(m,_) in zip(order,trace))==summary["wordpieces"]
                assert sum(a!=rows[i][4] for i,(_,a) in zip(order,trace))==summary["errors"]
        raw=read(f"{name}-raw-256.json.gz");norm=read(f"{name}-normalized-256.json.gz");bloom=read(f"{name}-bloom-256.json.gz")
        stale=read(f"{name}-title_only-0.json.gz")
        output[name]={"changed_title_since_previous":len(changed),"title_only_errors_at_changed":sum(stale[j][1]!=rows[order[j]][4] for j in changed),
                      "primary_reads_saved_pp":100*sum(a[0]-b[0] for a,b in zip(raw,bloom))/len(rows),
                      "raw_bloom_ci95_pp":interval(rows,order,raw,bloom),
                      "normalized_bloom_ci95_pp":interval(rows,order,norm,bloom)}
    put("audit.json",{"multi_version_titles":sum(len(v)>1 for v in rev_sets.values()),"checked_decisions":50*len(rows),"primary":output})
if __name__=="__main__":
    main()

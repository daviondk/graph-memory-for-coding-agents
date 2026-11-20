import sys, json, gzip,hashlib
from pathlib import Path
from collections import Counter,defaultdict
H=Path(__file__).resolve().parent;W=H.parents[1];P=W/"memory_session5/packets";sys.path.insert(0,str(P))
from extract5 import pq,OLD,ALLOWED
old={s for rs in json.load(open(P/"selection.json")).values() for s,k,i in rs}
old.update(s for s,k,i in json.load(open(P/"transfer/selection.json")))
old.update(s for s,k,i in json.load(open(W/"graph_memory_round2/span_memory/selection.json")))
for f in (OLD/"source").glob("*.gz"):
    for line in gzip.open(f,"rb"):
        old.add(json.loads(line)["instance"])
seen=set();c=Counter();extra=Counter()
for p in sorted((OLD/".scratch").glob("*.parquet")):
    pf=pq.ParquetFile(p)
    for b in pf.iter_batches(columns=['instance_id']):
        for x in b.to_pylist():
            i=x['instance_id'];r=i.split('.')[0]
            if i not in seen and i not in old:
                c[r]+=1
            seen.add(i)
    pf.close()
print("available",sum(c.values()));print(sorted(c.items(),key=lambda x:-x[1])[:120]);print("outside",sum(n for r,n in c.items() if r not in ALLOWED));print(sorted((r,n) for r,n in c.items() if r not in ALLOWED))

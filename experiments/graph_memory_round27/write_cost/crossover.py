"""Compute the observed stable break-even point per SQuAD article and panel."""
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent

def crossing(filename):
    records = json.loads(gzip.decompress((ROOT/filename).read_bytes()))
    groups = defaultdict(list)
    for rep,corpus,episode,method,ingest,queries in records:
        if corpus != "squad" or method not in ("raw","eager"):
            continue
        cost = ingest
        groups[episode,method,0].append(cost)
        for i,r in enumerate(queries,1):
            cost += r[1]
            groups[episode,method,i].append(cost)
    result = {}
    for key in sorted({k[0] for k in groups}):
        diff = []
        for i in range(12):
            a,b = (groups[key,m,i] for m in ("eager","raw"))
            assert len(a)==len(b)==3
            diff.append(median(a)-median(b))
        first = next((i for i in range(12) if diff[i] < 0),None)
        stable = next((i for i in range(12) if max(diff[i:]) < 0),None)
        result[key] = [first,stable]
    return result

def main():
    a,b = (crossing(f) for f in ("times.json.gz","promotion-times.json.gz"))
    assert a.keys()==b.keys() and len(a)==48
    numerics={name:dict(sorted(Counter(v[1] for v in r.values()).items())) for name,r in (("first",a),("control",b))}
    out={"per_article":{k:[*a[k],*b[k]] for k in a},"stable_histogram":numerics,
         "same":sum(a[k][1]==b[k][1] for k in a),"within_one":sum(abs(a[k][1]-b[k][1])<=1 for k in a)}
    (ROOT/"crossover.json").write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(numerics,out["same"],out["within_one"])
if __name__ == "__main__":
    main()


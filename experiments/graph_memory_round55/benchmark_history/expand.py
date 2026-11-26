"""Fetch actual catalog path membership and lock the out-of-shortlist choices before labelling."""
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
import tarfile
from extract import HERE,R54,save

ARC=Path("D:/CodexResearch/x20-r54-code-links/agent_retrieval_bench_v2_edit2ripple.tar.zst")
PATH = re.compile(rb'"path"\s*:\s*("(?:[^"\\]|\\.)*")')

def directories(bases):
    with ARC.open("rb") as f:
        import hashlib
        assert hashlib.file_digest(f,"sha256").hexdigest()==json.loads((R54/"source.json").read_bytes())["archive"]
    out={}
    with tarfile.open(ARC,"r|zst") as z:
        for m in z:
            if not m.name.startswith("./corpus/") or not m.name.endswith(".chunks.jsonl"):
                continue
            key=m.name.rsplit("/",1)[1].split(".")[0]
            if key not in bases:
                continue
            paths=set()
            for line in z.extractfile(m):
                match=PATH.search(line)
                # Check actual top-level JSON key for unusual lines.
                path=json.loads(match.group(1)) if match else json.loads(line)["path"]
                paths.add(path)
            out[key]=paths
    assert set(out)==set(bases)
    return out

def forecast(row,data,available):
    order=row["predictions"]["lexical"]
    assert set(order)<=available and len(available-{row["anchor"]})==row["pool_size"]
    counts,weights,corroborated,last,pop=Counter(),Counter(),Counter(),{},Counter()
    external=available-set(order)-{row["anchor"]}
    for age,(sha,m,paths) in enumerate(data):
        if not 2<=m<=20:
            continue
        extra=external.intersection(paths)
        agree=bool(set(order[:4]).intersection(paths))
        for p in extra:
            pop[p]+=1/(m-1)
            if row["anchor"] in paths:
                counts[p]+=1
                weights[p]+=1/(m-1)
                corroborated[p]+=int(agree)
                last.setdefault(p,age)
    evidence=sorted(counts,key=lambda p:(-weights[p],-corroborated[p],last[p],p))
    rules={"corroborated":[p for p in evidence if counts[p]>=2 or corroborated[p]],
           "twice":[p for p in evidence if counts[p]>=2],"once":evidence}
    rules["frequency"]=[max(sorted(pop),key=pop.get)] if rules["corroborated"] else []
    ranked={m:order[:4]+(v[:1] or order[4:5]) for m,v in rules.items()}
    ranked["lexical"]=order[:5]
    return dict(repo=row["repo"],ranked=ranked,evidence=[[p,counts[p],corroborated[p],weights[p],last[p]] for p in evidence],
                shortlist=order,base=row["commit"],available=len(available))

def main():
    history=json.load(gzip.open(HERE/"history.json.gz"))
    rows=json.load(gzip.open(R54/"forecasts.json.gz"))
    catalog=directories(history)
    out={q:forecast(r,history[r["commit"]]["history"],catalog[r["commit"]]) for q,r in sorted(rows.items())}
    save(HERE/"expanded-ranks.json.gz",out)
    paths=["EXPANSION_RU.md","expand.py","history.json.gz","expanded-ranks.json.gz"]
    save(HERE/"expanded-seal.json",{p:sha256((HERE/p).read_bytes()).hexdigest() for p in paths})
    print("verified corpus paths",sum(map(len,catalog.values())),"ranked",len(rows))
if __name__=="__main__":
    main()

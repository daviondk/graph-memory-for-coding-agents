"""Keep the original author's slots, including the observed anchor when it appears."""
import gzip
from hashlib import sha256
import json
import statistics
import sys
from expand import directories
from extract import HERE,R54,save
from grade import metric,paired

def freeze():
    history=json.load(gzip.open(HERE/"history.json.gz"))
    rows=json.load(gzip.open(R54/"forecasts.json.gz"))
    catalog=directories(history)
    out={}
    for q,r in sorted(rows.items()):
        order=r["published_raw"]["lexical"]
        assert len(set(order))==len(order)==20
        a=r["anchor"]
        others=set(order[:4])-{a}
        e={}
        for age,(sha,m,paths) in enumerate(history[r["commit"]]["history"]):
            if a not in paths:continue
            assert 2<=m<=20
            agree=bool(others.intersection(paths))
            for p in set(paths).intersection(catalog[r["commit"]])-set(order)-{a}:
                t=e.setdefault(p,[0,0,0.,age])
                t[0]+=1;t[1]+=int(agree);t[2]+=1/(m-1)
        eligible=sorted((p for p,t in e.items() if t[0]>=2 or t[1]),key=lambda p:(-e[p][2],-e[p][1],e[p][3],p))
        out[q]=dict(repo=r["repo"],lexical=order[:5],graph=order[:4]+(eligible[:1] or order[4:5]))
    save(HERE/"original-ranks.json.gz",out)
    save(HERE/"original-seal.json",{p:sha256((HERE/p).read_bytes()).hexdigest() for p in
                                    ("original_budget.py","ORIGINAL_RU.md","original-ranks.json.gz","history.json.gz")})

def grade():
    seal=json.loads((HERE/"original-seal.json").read_bytes())
    assert all(sha256((HERE/p).read_bytes()).hexdigest()==s for p,s in seal.items())
    runs=json.load(gzip.open(HERE/"original-ranks.json.gz"))
    import tarfile
    from expand import ARC
    with tarfile.open(ARC,"r|zst") as arc:
        for m in arc:
            if m.name=="./eval/v2_edit2ripple/lexical_details.jsonl":
                truths={r["sample_id"]:(r["gold_files"],r["metrics"]["Recall@5"]) for r in map(json.loads,arc.extractfile(m))}
                break
    rows={}
    for q,r in runs.items():
        vals={k:metric(r[k],truths[q][0]) for k in ("graph","lexical")}
        assert abs(vals["lexical"][0]-truths[q][1])<1e-8
        rows[q]=dict(repo=r["repo"],scores=vals)
    means={k:list(map(statistics.fmean,zip(*(r["scores"][k] for r in rows.values())))) for k in ("lexical","graph")}
    out={"n":len(rows),"means":means,"primary":paired(rows,"graph","lexical"),"switched":sum(x["graph"]!=x["lexical"] for x in runs.values())}
    save(HERE/"original-results.json",out)
    print(out)
if __name__=="__main__":
    if sys.argv[1]=="freeze":freeze()
    else:grade()

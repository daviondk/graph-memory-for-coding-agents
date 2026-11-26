from collections import Counter
import gzip
from hashlib import sha256
import json
import random
import statistics
from extract import HERE,R54,save
from predict import select

def metric(ranked, gold):
    indices=[i+1 for i,p in enumerate(ranked) if p in gold]
    return [len(indices)/len(gold),float(bool(indices)),1/min(indices) if indices else 0]

def paired(rows,a,b):
    grouped={}
    for r in rows.values():
        grouped.setdefault(r["repo"],[]).append(r["scores"][a][0]-r["scores"][b][0])
    totals={repo:(len(ds),sum(ds)) for repo,ds in grouped.items()}
    delta=sum(s for _,s in totals.values())/len(rows)
    rng=random.Random(55031)
    sample=[]
    repos=sorted(totals)
    for _ in range(20000):
        blocks=rng.choices(repos,k=len(repos))
        sample.append(sum(totals[r][1] for r in blocks)/sum(totals[r][0] for r in blocks))
    sample.sort()
    ds=[d for batch in grouped.values() for d in batch]
    return dict(delta=delta,interval=[sample[499],sample[19499]],win=sum(x>0 for x in ds),
                loss=sum(x<0 for x in ds),tie=sum(x==0 for x in ds))

def main():
    seal=json.loads((HERE/"selection.json").read_bytes())
    assert all(sha256((HERE/p).read_bytes()).hexdigest()==v for p,v in seal.items())
    old=json.load(gzip.open(R54/"forecasts.json.gz"))
    obs=json.load(gzip.open(HERE/"history.json.gz"))
    runs=json.load(gzip.open(HERE/"ranks.json.gz"))
    assert all(r==select(old[q],obs[r["base"]]["history"]) for q,r in runs.items())
    truth=json.load(gzip.open(R54/"graded-rows.json.gz"))
    assert set(runs)==set(truth)
    rows={}
    for q,r in runs.items():
        gold=truth[q]["gold"]
        vals={m:metric(rank,gold) for m,rank in r["ranked"].items()}
        for m in ("bm25","repomap","lexical"):
            assert abs(vals[m][0]-truth[q]["graded"][m]["recall5"])<1e-12
        rows[q]=dict(repo=r["repo"],gold=gold,scores=vals)
    methods=list(next(iter(rows.values()))["scores"])
    out=dict(n=len(rows),bases=len(obs),repos=len(set(r["repo"] for r in rows.values())),
             columns=["Recall@5","Hit@5","MRR@5"],
             means={m:list(map(statistics.fmean,zip(*(r["scores"][m] for r in rows.values())))) for m in methods},
             contrasts={b:paired(rows,"graph2",b) for b in methods if b!="graph2"},
             changed={m:sum(set(r["ranked"][m])!=set(r["ranked"]["lexical"]) for r in runs.values()) for m in methods},
             graph_available=sum(r["eligible"] for r in runs.values()),
             support=dict(Counter(str(min(2,len(r["witness"]))) for r in runs.values())),
             reachable=statistics.fmean(len(set(truth[q]["gold"])&set(r["shortlist"]))/len(truth[q]["gold"]) for q,r in runs.items()),
             per_repo={repo:{m:statistics.fmean(r["scores"][m][0] for r in rows.values() if r["repo"]==repo)
                             for m in methods} for repo in sorted({r["repo"] for r in rows.values()})})
    save(HERE/"graded.json.gz",rows)
    save(HERE/"results.json",out)
    print(json.dumps({k:v for k,v in out.items() if k!="per_repo"}))

if __name__=="__main__":
    main()

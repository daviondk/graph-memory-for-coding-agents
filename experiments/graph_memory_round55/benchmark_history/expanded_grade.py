"""Grade the separately locked extension on candidate discovery."""
import gzip
from hashlib import sha256
import json
import statistics
from extract import HERE,R54,save
from grade import metric,paired

def main():
    seal = json.loads((HERE/"expanded-seal.json").read_bytes())
    assert all(sha256((HERE/k).read_bytes()).hexdigest()==v for k,v in seal.items())
    runs = json.load(gzip.open(HERE/"expanded-ranks.json.gz"))
    truth = json.load(gzip.open(R54/"graded-rows.json.gz"))
    assert set(runs)==set(truth)
    rows={}
    outside_found=[]
    outside_count=outside_hit=0
    for q,r in runs.items():
        gold = set(truth[q]["gold"])
        scores = {m:metric(rank,gold) for m,rank in r["ranked"].items()}
        assert scores["lexical"][0]==truth[q]["graded"]["lexical"]["recall5"]
        outside=gold-set(r["shortlist"])
        extra=outside.intersection(x[0] for x in r["evidence"])
        outside_count+=len(outside)
        outside_hit+=len(extra)
        if extra:outside_found.append(q)
        rows[q]=dict(repo=r["repo"],scores=scores,reachable_external=sorted(extra),gold=sorted(gold))
    methods=list(next(iter(rows.values()))["scores"])
    out=dict(n=len(rows),means={m:list(map(statistics.fmean,zip(*(r["scores"][m] for r in rows.values())))) for m in methods},
             contrasts={m:paired(rows,"corroborated",m) for m in methods if m!="corroborated"},
             changes={m:sum(r["ranked"][m]!=r["ranked"]["lexical"] for r in runs.values()) for m in methods},
             missing_pairs=outside_count,reachable_pairs=outside_hit,reachable_tasks=outside_found,
             opened_tasks={m:[q for q,r in runs.items() if r["ranked"][m]!=r["ranked"]["lexical"]]
                           for m in methods if m!="lexical"})
    save(HERE/"expanded-results.json",out)
    save(HERE/"expanded-graded.json.gz",rows)
    print(out["means"],out["contrasts"],out["changes"],outside_hit,outside_count,len(outside_found))
if __name__=="__main__":
    main()

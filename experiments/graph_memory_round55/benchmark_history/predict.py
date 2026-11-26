"""Fixed five additional reads, from the same frozen shortlist for all re-rankers."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from extract import HERE,R54,save

def promote(order, votes, mass, threshold):
    allowed=[x for x in order[4:] if votes[x]>=threshold]
    if not allowed:
        return order[:5],False
    # Candidates tied on evidence retain their earlier rank.
    best=max(allowed,key=lambda p:mass[p])
    return order[:4]+[best],True

def select(row, history):
    order=row["predictions"]["lexical"]
    anchor=row["anchor"]
    assert anchor not in order and len(set(order))==len(order)==20
    count,weight,pop,popw=Counter(),Counter(),Counter(),Counter()
    witness=[]
    for sha,m,paths in history:
        if not 2<=m<=20:continue
        assert len(paths)==m
        candidates=set(order).intersection(paths)
        for p in candidates:
            pop[p]+=1
            popw[p]+=1/(m-1)
        if anchor in paths:
            witness.append(sha)
            for p in candidates:
                count[p]+=1
                weight[p]+=1/(m-1)
    graph,has=promote(order,count,weight,2)
    popular=promote(order,pop,popw,2)[0]
    methods={"lexical":order[:5],"graph2":graph,"graph1":promote(order,count,weight,1)[0],
             "frequency":popular,"matched_frequency":popular if has else order[:5],
             "repomap":row["predictions"]["repomap"][:5],"bm25":row["predictions"]["bm25"][:5]}
    return dict(repo=row["repo"],base=row["commit"],anchor=anchor,depth=len(history),
                witness=witness,eligible=has,shortlist=order,candidate_evidence=[
                    [p,count[p],weight[p],pop[p],popw[p]] for p in order],ranked=methods)

def main():
    obs=json.load(gzip.open(HERE/"history.json.gz"))
    old=json.load(gzip.open(R54/"forecasts.json.gz"))
    forecasts={q:select(r,obs[r["commit"]]["history"]) for q,r in sorted(old.items())}
    save(HERE/"ranks.json.gz",forecasts)
    names=["history.json.gz","ranks.json.gz","extract.py","predict.py","PROTOCOL_RU.md"]
    save(HERE/"selection.json",{p:sha256((HERE/p).read_bytes()).hexdigest() for p in names})
    print("Ranked",len(forecasts))

if __name__=="__main__":
    main()

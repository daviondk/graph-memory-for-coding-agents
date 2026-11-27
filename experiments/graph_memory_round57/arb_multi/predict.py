"""Freeze graph-ranking interventions before joining any results to benchmark labels."""
from collections import Counter,defaultdict
from fractions import Fraction
from itertools import combinations
from math import comb
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
OLD=HERE.parents[1]/"graph_memory_round56"/"code2test"
sys.path.insert(0,str(OLD))
from source import read,save,digest
from additive import rowsplit
from rank import past_groups

def fuse(paths,ranks,static):
    scores=static.copy();ix={p:i for i,p in enumerate(paths)}
    for k,p in enumerate(ranks[:20],1):scores[ix[p]]+=11/(10+k)
    return [paths[i] for i in np.argsort(-scores,kind="stable")[:5]]

def main():
    hist=read(OLD/"histories.json.gz");roster=read(OLD/"roster.json")
    old=read(OLD/"additive-ranks.json.gz");auth=read(OLD/"role-ranks.json.gz")
    common=read(OLD/"predictions.json.gz");samples={}
    for q,r in rowsplit("code2test"):
        base=r["base"];repo=r["repo"];anchors=set(roster[q]["anchors"])
        paths=r["paths"];pool=set(paths)-anchors
        selected=past_groups(hist[base]["history"],anchors,"local8")
        seen=set();linear=Counter();pair=defaultdict(Fraction);age_by={}
        witnesses=[];read_members=0
        for age,sha,m,event in selected:
            assert sha not in seen and len(event)==len(set(event))
            seen.add(sha);read_members+=len(event)
            seeds=sorted(anchors.intersection(event))
            assert seeds
            tests=sorted(pool.intersection(event));k=len(seeds)
            witnesses.append(dict(sha=sha,age=age,m=m,decoded=len(event),seeds=seeds,tests=tests))
            for test in tests:
                linear[test]+=1/(m-1)
                pair[test]+=Fraction(comb(k,2),m-1)
                age_by.setdefault(test,age)
        ordered=sorted(linear,key=lambda p:(-linear[p],age_by[p],p))
        altered=sorted(linear,key=lambda p:(-pair[p],-linear[p],age_by[p],p))
        static=r["mats"]["static"][:,[0,1,3,4,6]].sum(1)
        ranks={"base":fuse(paths,[],static),"linear":fuse(paths,ordered,static),"pair":fuse(paths,altered,static)}
        assert ranks["base"]==old[q]["base"] and ranks["linear"]==old[q]["base_history"]
        ranks["tests_only_repomap"]=auth[q]["new"]["repomap"]
        for m in ("embed4","codenib_dense","oko1","oko2","oko3"):
            ranks[m]=common[q]["ranked"]["new"][m]
        if not any(pair.values()):assert ordered==altered and ranks["linear"]==ranks["pair"]
        samples[q]=dict(repo=repo,base=base,seeds=sorted(anchors),events=witnesses,
                        event_count=len(witnesses),members=read_members,
                        multisource=any(len(e["seeds"])>=2 for e in witnesses),
                        test_supported=sum(v>0 for v in pair.values()),
                        multi_test_events=sum(len(e["seeds"])>=2 and bool(e["tests"]) for e in witnesses),
                        graph=ordered,graph_pair=altered,ranks=ranks)
    assert len(samples)==105
    save(HERE/"ranks.json.gz",samples)
    sources=("additive.py","rank.py","roster.json","catalog.json.gz","histories.json.gz",
             "publisher.json.gz","community.json.gz","role-author.json.gz","role-ranks.json.gz",
             "additive-ranks.json.gz","predictions.json.gz")
    save(HERE/"seal.json",{"inputs":{n:digest(OLD/n) for n in sources},
                           "local":{n:digest(HERE/n) for n in ("PROTOCOL_RU.md","predict.py","ranks.json.gz")}})
    print("Sealed",len(samples),"predictions without loading gold.")
if __name__=="__main__":main()

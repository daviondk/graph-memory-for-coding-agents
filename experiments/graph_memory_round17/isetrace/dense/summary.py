"""Verify native dense selections, compare BM25 on the same examples, and summarize paired results."""
from pathlib import Path
import collections
import json
import sys
from statistics import mean
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from summarize import load,matched
from verify_records import metrics,hash_

def main():
    for manifest in ("plan-seal.json","dense-predictions-seal.json"):
        for n,h in load(ROOT/manifest).items():assert hash_(ROOT/n)==h
    outcome=load(ROOT/"outcomes.json.gz")
    indexed=collections.defaultdict(dict)
    for r in outcome:indexed[r["shard"],r["ranker"],r["budget"],r["policy"]][r["query"]]=r
    chosen=load(ROOT/"selection.json")
    labels={}
    for i,p in enumerate((ROOT.parent,ROOT.parent/"replication")):
        group={q for qs in chosen[str(i)].values() for q in qs}
        archive=load(p/"gold-spans.json.gz")
        labels.update({q:archive[q] for q in group})
        assert set(indexed[i,"bm25",2048,"prefix"])==set(indexed[i,"dense",2048,"prefix"])==group
    ranks={r["query"]:r for r in load(ROOT/"ranked.json.gz")}
    for sets in load(ROOT/"sets.json.gz"):
        q=sets["q"]
        src=ranks[q]
        by_id={r["node_id"]:r for r in src["ranking"]}
        for b,arms in sets["sets"].items():
            for name,ids in arms.items():
                kept=[by_id[i] for i in ids]
                out=indexed[src["shard"],"dense",int(b),name][q]
                expected=metrics(labels[q],kept)
                assert sum(n["token_count"] for n in kept)==out["tokens"]<=int(b)
                assert all(abs(a-out[f])<1e-12 for a,f in zip(expected,("coverage","density","full_support"),strict=True))
    summaries={}; comparisons={}
    for i in (0,1,"all"):
        def subset(r,b,h):
            return indexed[i,r,b,h] if i!="all" else {**indexed[0,r,b,h],**indexed[1,r,b,h]}
        for b in (512,1024,2048):
            for r in ("bm25","dense"):
                for h in ("prefix","skip","value","related"):
                    stats=list(subset(r,b,h).values())
                    summaries[f"{i}/{r}/{b}/{h}"]={**{m:mean(e[m] for e in stats) for m in ("full_support","tokens","coverage","density","f1")},"n":len(stats),"full":int(sum(e["full_support"] for e in stats))}
                for left,right in (("skip","prefix"),("related","skip"),("value","skip"),("related","value")):
                    comparisons[f"{i}/{r}/{b}/{left}-{right}"]=matched(subset(r,b,left),subset(r,b,right))
            for h in ("prefix","skip","value","related"):
                comparisons[f"{i}/dense-bm25/{b}/{h}"]=matched(subset("dense",b,h),subset("bm25",b,h))
    data={"summaries":summaries,"contrasts":comparisons}
    target=ROOT/"summary.json";target.write_text(json.dumps(data,indent=2)+"\n",encoding="utf8")
    for k,v in summaries.items():
        if "/2048/" in k:print(k,"N",v["n"],"full",v["full"],"coverage",round(v["coverage"],3),"spent",round(v["tokens"]))
    print("dense skip-prefix",comparisons["all/dense/2048/skip-prefix"])
if __name__=="__main__":main()

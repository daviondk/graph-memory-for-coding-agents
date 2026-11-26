"""Independent checks from saved projections. Recompute the primary decision directly per query."""
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import PurePosixPath
import re
import statistics
import tarfile
from source import ARC,HERE,R55,read,save,digest
from rank import is_test
from grade import compare

def metrics(rank,gold):
    hits=[j for j,x in enumerate(rank[:5],1) if x in gold]
    return sum(p in gold for p in rank[:5])/len(gold),int(bool(hits)),1/hits[0] if hits else 0.

def main():
    runs=read(HERE/"predictions.json.gz");roster=read(HERE/"roster.json");labels=read(HERE/"ground-truth.json.gz")
    hist=read(HERE/"histories.json.gz");paths=read(HERE/"catalog.json.gz");graded=read(HERE/"graded.json.gz")
    extras=read(HERE/"additive-ranks.json.gz");fitted=read(HERE/"additive-fits.json");additional=read(HERE/"additive-graded.json.gz")
    role=read(HERE/"role-ranks.json.gz");saved=read(HERE/"binding-results.json")
    assert sum(int(r["votes"]) for r in read(HERE/"binding-events.json.gz").values())==saved["votes"]
    lookup={q:set(r["anchors"]) for q,r in roster.items()}
    raw_inputs={}
    with tarfile.open(ARC,"r|zst") as tar:
        for m in tar:
            if m.name.endswith("/samples.jsonl"):
                for raw in map(json.loads,tar.extractfile(m)):
                    if raw["id"] in runs:
                        text=json.dumps(raw["query"],ensure_ascii=False)
                        raw_inputs[raw["id"]]=text
                break
    assert set(raw_inputs)==set(runs)
    n_metrics=0;decisions=0;tagged={};epochs=set()
    for q,r in runs.items():
        gold=set(labels[q]);available=set(paths[r["base"]]);anchors=lookup[q];stream=hist[r["base"]]["history"]
        assert len(stream)==64 and stream[0][0]==r["base"] and all(gold<=available for _ in (0,))
        epochs.update(s for s,_,_ in stream)
        assert len({s for s,_,_ in stream})==64
        target=lambda word:re.search(r"(?<![\w/.-])"+re.escape(word)+r"(?![\w/.-])",raw_inputs[q],re.IGNORECASE) is not None
        tagged[q]=dict(full=any(target(p) for p in gold),basename=any(target(PurePosixPath(p).name) for p in gold),
                       anchored=any(target(p) for p in anchors))
        for mode in ("new","original"):
            ranks=r["ranked"][mode]
            for method,v in ranks.items():
                assert len(set(v))==len(v)==5 and set(v)<=available
                if mode=="new":assert not set(v)&anchors
                observed=metrics(v,gold);stored=graded[mode][q]["metrics"][method]
                assert all(abs(x-y)<1e-12 for x,y in zip(observed,stored))
                n_metrics+=1
            top=r["evidence"][mode]["all20"]
            base=set(top[:4])-anchors
            per_anchor={a:[i for i,(_,_,p) in enumerate(stream) if a in p][:8] for a in anchors}
            groups=sorted(set().union(*map(set,per_anchor.values())))
            counts={};last={};strength={};joint=Counter()
            for i in groups:
                _,m,p=stream[i]
                for dest in p:
                    if dest in top or dest in anchors or dest not in available or not is_test(dest):continue
                    counts[dest]=1+counts.get(dest,0);last.setdefault(dest,i)
                    strength[dest]=strength.get(dest,0.)+1/(m-1)
                    joint[dest]+=bool(base.intersection(p))
            qualified=sorted((p for p,n in counts.items() if n>=2 or joint[p]),key=lambda p:(-strength[p],-joint[p],last[p],p))
            assert qualified==r["evidence"][mode]["qualified"]
            assert ranks["role_embed4_local8"]==top[:4]+(qualified[:1] or top[4:5])
            decisions+=1
        for m,ls in extras[q].items():
            assert len(set(ls))==5 and set(ls)<=available
            assert list(metrics(ls,gold))==additional[q]["metrics"][m][:3]
        for p in role[q].values():
            assert all(set(v)<=available for v in p.values())
    assert all(r["max_abs_gradient"]<1e-7 for f in fitted.values() for r in f.values())
    key="base_history__base"
    source=read(HERE/"additive-results.json")["comparisons"][key]
    assert source==compare(list(additional.values()),"base_history","base")
    missing_full=[q for q,t in tagged.items() if not t["full"]]
    missing_both=[q for q,t in tagged.items() if not(t["full"] or t["basename"])]
    panels={}
    for name,keys in (("no_literal_target_path",missing_full),("no_literal_target_path_or_basename",missing_both)):
        rs=[graded["new"][q] for q in keys];ss=[additional[q] for q in keys]
        panels[name]={"n":len(keys),"primary":compare(rs,"role_embed4_local8","role_embed4"),
                      "secondary":compare(ss,"base_history","base")}
    out=dict(primary_decisions=decisions,checked_ranked_lists=n_metrics,canonical106=read(HERE/"canonical-v2.json")["matching_ids"],
             unique_history_shas=len(epochs),nonempty_history=sum(bool(r["consulted"]["g64"]) for r in runs.values()),
             cap_bound=sum(r["consulted"]["g64"]>r["consulted"]["local8"] for r in runs.values()),
             literal_full=sum(t["full"] for t in tagged.values()),literal_basename=sum(t["basename"] for t in tagged.values()),
             grad_checks=sum(map(len,fitted.values())),panels=panels)
    save(HERE/"audit.json",out)
    print(out)
if __name__=="__main__":main()

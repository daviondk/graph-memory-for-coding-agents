"""Audit placebo balance without opening labels or model answers."""
from pathlib import Path
from statistics import mean,median
from paths50 import *
from rewire import catalog
def main():
    assert get(D50/"retrieval-seal.json")["orders"]==sha(D50/"orders.json.gz")
    assert get(D50/"input-seal.json")["contexts"]==sha(D50/"contexts.json.gz")
    view=get(P50/"visible.json.gz");ctx=get(D50/"contexts.json.gz");obs=get(D50/"orders.json.gz")
    rows={str(s):[] for s in SEEDS};all_diffs=[];length_equal=0;stored=0
    for q,d in obs.items():
        question,docs=view[q];seq,_,_=catalog(question,[p[1] for p in docs]);c=ctx[q]
        rank={i:j for j,i in enumerate(d["order"])}
        for seed,decoy in d["sham"].items():
            old=d["true"];new=decoy["second"]
            assert len(d["edges"])==len(decoy["edges"]) and sorted(d["edges"].values())==sorted(decoy["edges"].values()) and (old!=d["lex"])==(new!=d["lex"])
            assert c["refs"]["true"][2]==c["refs"]["sham"+seed][2]
            if old!=new:
                a,b=len(seq[old]),len(seq[new]);delta=[abs(rank[new]-rank[old]),abs(d["question_rank"][str(new)]-d["question_rank"][str(old)]),
                     abs(d["snippet_rank"][str(new)]-d["snippet_rank"][str(old)]),abs(a-b)]
                rows[seed].append(delta);all_diffs.append(delta);length_equal+=a==b
            stored+=1
    def stats(z):
        return dict(draws=len(z),mean=[mean(x) for x in zip(*z)],median=[median(x) for x in zip(*z)])
    put(D50/"matching.json",dict(columns=["abs_expanded_rank","abs_query_rank","abs_snippet_rank","abs_title_word_count"],all=stats(all_diffs),
        per_seed={k:stats(v) for k,v in rows.items()},identical_title_length_redirected=length_equal,identical_full_context_tokens=stored,
        retrieval=sha(D50/"retrieval-seal.json"),input=sha(D50/"input-seal.json")))
    print(stats(all_diffs),length_equal,stored)
if __name__=="__main__":main()

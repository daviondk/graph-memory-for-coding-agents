"""Offline audit of paired exposures, degree-preserving relabeling and all counts."""
from collections import Counter
import hashlib
import struct
from roster import HERE, get, sha


def main():
    g=get(HERE/"graph-seal.json");p=get(HERE/"prompt-seal.json");e=get(HERE/"answer-seal.json")
    assert all(sha(HERE/f)==h for f,h in {**p["hashes"],**e}.items())
    assert all(g[k]==sha(HERE/n) for k,n in (("protocol","PROTOCOL_RU.md"),("cohort","cohort.json.gz"),("graph","graph.json.gz")))
    inp=get(HERE/"inputs.json.gz");ans=get(HERE/"answers.json.gz");assign=get(HERE/"assignments.json.gz")
    scores=get(HERE/"scored.json.gz");summary=get(HERE/"results.json");graphs=get(HERE/"graph.json.gz")
    assert set(inp)==set(ans)
    assert all(hashlib.sha256(struct.pack(f"<{len(x)}I",*x)).hexdigest()==h for h,x in inp.items())
    for rec in graphs.values():
        edges=rec["edges"];assert len(edges)<=6 and len(set(map(tuple,edges)))==len(edges)
        targets=[b for a,b in edges]
        shifted=[(a,targets[(i+1)%len(edges)]) for i,(a,b) in enumerate(edges)]
        assert Counter(a for a,b in edges)==Counter(a for a,b in shifted)
        assert Counter(b for a,b in edges)==Counter(b for a,b in shifted)
    for q,r in assign.items():
        hs=r["arms"];assert len(set(len(inp[h]) for h in hs.values()))==1
        assert sorted(r["base"])==sorted(r["order"])
        for arm,h in hs.items():
            digit=ans[h]["text"].strip()
            choice=r["order"][int(digit)-1] if digit in ("1","2","3","4","5") else r["base"][0]
            assert scores[q]["choice"][arm]==choice
    labels=list(next(iter(scores.values()))["hit"])
    assert summary["match1"]=={a:sum(r["hit"][a] for r in scores.values()) for a in labels}
    assert summary["slate5"]==sum(r["in_slate"] for r in scores.values())
    assert summary["distinct_prompts"]==len(inp)
    assert sum(summary["match1"][a] for a in ("true","flat","rotation"))==133
    print("Verified",len(graphs),"graphs,",len(scores),"questions,",len(inp),"distinct GPU prompts and the primary paired comparisons.")


if __name__=="__main__":main()

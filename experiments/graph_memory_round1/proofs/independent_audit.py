"""Independently reconstruct paired counts and check invariants of stored certificates."""
from pathlib import Path
import gzip,hashlib,itertools,json
from run import full_truth,recheck
ROOT=Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def data(folder, meta, name):
    path=folder/"shards"/(name+".jsonl.gz")
    assert digest(path)==meta["sha256"]
    return [json.loads(x) for x in gzip.decompress(path.read_bytes()).splitlines() if x]

def sanity():
    one=("a","b","d")
    two=("a","c","d")
    base={v:(v+".py","old"+v) for v in "abcd"}
    g={"a":("b","c"),"b":("d",),"c":("d",),"d":()}
    cases=0
    # All 16 edge-removal patterns, then zero or one deleted module, including endpoints.
    for state in itertools.product([False,True],repeat=4):
        edges=[("a","b"),("a","c"),("b","d"),("c","d")]
        for absent in [None,*"abcd"]:
            h={u:tuple(v for (a,v),keep in zip(edges,state) if a==u and keep and v!=absent)
               for u in "abcd" if u!=absent}
            # Removing a provider can invalidate incoming edges despite an unchanged source.
            new={u:(u+".py",("new" if any(a==u and not z for (a,v),z in zip(edges,state)) else "old")+u)
                 for u in h}
            expected=any(all(v in h for v in p) and all(v in h[u] for u,v in zip(p,p[1:])) for p in (one,two))
            assert full_truth(h,"a","d")==expected
            got=recheck([one,two],base,new,h,expected)
            assert not got["fast"] or expected
            cases+=1
    return cases

def main():
    counts={}
    for label,folder in [("AB",ROOT),("C",ROOT/"transfer")]:
        meta=json.loads((folder/"receipt.json").read_text())
        total=lost=wins=losses=0
        for repo in meta["repositories"]:
            rows=data(folder,repo,repo["repo"])
            assert len(rows)==repo["rows"]
            assert len({(r["before"],r["after"],r["s"],r["t"]) for r in rows})==len(rows)
            for r in rows:
                assert 1<=r["alternatives"]<=16
                for policy in ("one","short3","diverse","historical"):
                    a=r[policy]
                    assert 1<=len(a["proofs"])<=3
                    for p in a["proofs"]:
                        assert p[0]==r["s"] and p[-1]==r["t"] and 3<=len(p)<=5 and len(p)==len(set(p))
                    assert a["fast"]<=a["validated"]<=r["truth"]
                    assert a["reads"]>=0 and (not a["fast"] or a["reads"]==0)
                assert r["one"]["proofs"][0] in r["short3"]["proofs"]
                assert r["short3"]["fast"]>=r["one"]["fast"]
                a=r["historical"]["fast"];b=r["short3"]["fast"]
                wins+=a>b;losses+=a<b
                total+=1;lost+=not r["truth"]
        obj=json.loads((folder/"results.json").read_text())
        if label=="AB":
            comp=obj["all"]["differences"]["historical-short3"]
            assert [total,lost,wins,losses]==[obj["all"]["queries"],obj["all"]["gold_lost"],comp["paired_win"],comp["paired_loss"]]
        else:
            s=obj["totals"]
            assert [total,lost,wins,losses]==[s["n"],s["lost"],s["history_wins"],s["history_losses"]]
        counts[label]=dict(n=total,lost=lost,wins=wins,losses=losses,shards=len(meta["repositories"]))
    out={"audited":counts,"exhaustive_tiny_worlds":sanity(),"fingerprints":{p:digest(ROOT/p) for p in
         ("PROTOCOL.md","run.py","score.py","input_lock.json","results.json","transfer/transfer.py",
          "transfer/PROTOCOL.md","transfer/input_lock.json","transfer/results.json")}}
    (ROOT/"audit.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(out["audited"],out["exhaustive_tiny_worlds"])
if __name__=="__main__":main()


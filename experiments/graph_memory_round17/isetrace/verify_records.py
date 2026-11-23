"""Verify sealed inputs and the exact cost, nesting and source support of all archived actions."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parent
def load(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)
def hash_(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def interval_map(spans):
    groups=collections.defaultdict(list)
    for s in spans:groups[s["event_id"],s["json_pointer"]].append((s["char_start"],s["char_end"]))
    merged={}
    for k,lengths in groups.items():
        terms=[]
        for start,end in sorted(lengths):
            if terms and start<=terms[-1][1]:terms[-1]=(terms[-1][0],max(end,terms[-1][1]))
            else:terms.append((start,end))
        merged[k]=terms
    return merged
def metrics(gold,nodes):
    spans=[s for v in nodes for s in v["source_spans"]]
    pred=interval_map(spans);target=interval_map(gold)
    gold_size=sum(e-s for pairs in target.values() for s,e in pairs)
    cost=sum(s["char_end"]-s["char_start"] for s in spans)
    covered=sum(max(0,min(ge,pe)-max(gs,ps)) for key,pairs in target.items()
                for gs,ge in pairs for ps,pe in pred.get(key,[]))
    coverage=covered/gold_size;density=covered/cost if cost else 0
    return coverage,density,float(covered==gold_size)
def verify(p):
    for m in ("assignment.json","prediction-seal.json"):
        for n,h in load(p/m).items():assert hash_(p/n)==h
    ranks={(r["q"],r["v"]):r["ranking"] for r in load(p/"native-ranks.json.gz")}
    results={(r["query"],r["view"],r["budget"],r["policy"]):r for r in load(p/"outcomes.json.gz")}
    sets=load(p/"selections.json.gz");gold=load(p/"gold-spans.json.gz")
    assert len(results)==21*len(sets)==21*len(gold)
    for task in sets:
        q=task["query"]
        for v,budgets in task["sets"].items():
            order=ranks[q,v];index={r["node_id"]:r for r in order}
            for budget,arms in budgets.items():
                b=int(budget);prefix=arms["prefix"]
                assert prefix==[r["node_id"] for r in order[:len(prefix)]]
                if len(prefix)<len(order):assert sum(r["token_count"] for r in order[:len(prefix)+1])>b
                for arm,selected in arms.items():
                    assert selected[:len(prefix)]==prefix
                    assert len(set(selected))==len(selected)
                    nodes=[index[k] for k in selected];used=sum(r["token_count"] for r in nodes)
                    out=results[q,v,b,arm];assert used==out["tokens"] and used<=b
                    for field,value in zip(("coverage","density","full_support"),metrics(gold[q],nodes),strict=True):
                        assert abs(value-out[field])<1e-12
    summary=load(p/"results.json")
    assert summary["n"]==len(sets)
    for key,ms in summary["means"].items():
        b,v,h=key.split("/")
        records=[out for (q,view,budget,arm),out in results.items() if view==v and budget==int(b) and arm==h]
        assert len(records)==len(sets)
        for f in ("full_support","coverage","density","tokens","nodes"):assert abs(mean(r[f] for r in records)-ms[f])<1e-12
    return len(sets),len(results)
if __name__=="__main__":
    a=verify(ROOT);b=verify(ROOT/"replication");print("queries",a[0]+b[0],"scored records",a[1]+b[1])

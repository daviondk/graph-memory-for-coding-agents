"""Test a pre-specified mechanism on sealed outcomes. Never supply gold support to the selectors."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/"isetrace_official"
FILES={"gold":SOURCE/"gold-spans.json.gz","outcomes":SOURCE/"outcomes.json.gz",
       "protocol":ROOT/"PROTOCOL_RU.md","analysis":Path(__file__)}
CLASSES=("arguments_and_result_only","multiple_calls_with_complete_pair","multiple_calls_without_complete_pair","one_event")
MODES=("fewer", "equal", "more")


def save(name, obj):
    data=json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False).encode("utf8")+b"\n"
    (ROOT/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)


def event_class(spans):
    sides=defaultdict(set)
    for s in spans:
        match=re.fullmatch(r"(.+?):(call|output):(.+)",s["event_id"])
        assert match
        sides[(match[1],match[3])].add(match[2])
    assert sides
    pair=any(len(roles)==2 for roles in sides.values())
    if len(sides)==1:
        return CLASSES[0] if pair else CLASSES[3]
    return CLASSES[1] if pair else CLASSES[2]


def aggregate(rows):
    n=len(rows)
    if n==0:
        return dict(n=0)
    win=sum(r["delta"]>0 for r in rows)
    loss=sum(r["delta"]<0 for r in rows)
    return dict(n=n, trajectories=len({r["t"] for r in rows}), pair=sum(r["pair"] for r in rows),
                cost=sum(r["cost"] for r in rows), win=win, loss=loss, ties=n-win-loss,
                diff=(win-loss)/n, diff_coverage=sum(r["dcov"] for r in rows)/n,
                pair_tokens=sum(r["ptok"] for r in rows)/n, cost_tokens=sum(r["ctok"] for r in rows)/n)


def analyze():
    frozen=json.loads((ROOT/"lock.json").read_bytes())
    assert {k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in FILES.items()}==frozen
    labels=json.loads(gzip.decompress(FILES["gold"].read_bytes()))
    forecasts=json.loads(gzip.decompress(FILES["outcomes"].read_bytes()))
    arms=defaultdict(dict)
    for r in forecasts:
        if r["view"]=="provenance" and r["arm"] in ("value","related"):
            assert r["arm"] not in arms[r["q"]]
            arms[r["q"]][r["arm"]]=r
    assert len(arms)==2000 and set(arms)==set(labels)
    rows=[]
    for q,methods in sorted(arms.items()):
        a,b=methods["related"],methods["value"]
        assert a["t"]==b["t"]
        cls=event_class(labels[q])
        pa,co=int(a["full_support"]),int(b["full_support"])
        ptoken,ctoken=a["tokens"],b["tokens"]
        rows.append(dict(q=q,t=a["t"],cls=cls,pair=pa,cost=co,delta=pa-co,dcov=a["coverage"]-b["coverage"],
                         ptok=ptoken,ctok=ctoken,volume=MODES[0] if ptoken<ctoken else MODES[1] if ptoken==ctoken else MODES[2]))
    groups={s:[r for r in rows if r["cls"]==s] for s in CLASSES}
    groups.update({s:[r for r in rows if r["volume"]==s] for s in MODES})
    groups.update(has_pair=[r for r in rows if r["cls"] in CLASSES[:2]],
                  lacks_pair=[r for r in rows if r["cls"] in CLASSES[2:]],all=rows)
    summaries={s:aggregate(rs) for s,rs in groups.items()}
    tids=sorted({r["t"] for r in rows})
    ix={t:i for i,t in enumerate(tids)}
    names=list(groups)
    quantities=np.zeros((len(tids),2*len(names)),dtype=np.int32)
    for j,(_,batch) in enumerate(groups.items()):
        for r in batch:
            quantities[ix[r["t"]],2*j:2*j+2]+=(r["delta"],1)
    rand=np.random.default_rng(13)
    draws=[]
    for _ in range(100):
        sample=rand.integers(len(tids),size=(100,len(tids)))
        summed=quantities[sample].sum(axis=1)
        ratios=np.divide(summed[:,0::2],summed[:,1::2],out=np.full((100,len(names)),np.nan),where=summed[:,1::2]!=0)
        draws.append(ratios)
    distributions=np.concatenate(draws,axis=0)
    for j,name in enumerate(names):
        valid=distributions[np.isfinite(distributions[:,j]),j]
        if len(valid)>0:
            summaries[name]["ci95"]=np.quantile(valid,[.025,.975]).tolist()
    effects=distributions[:,names.index("has_pair")]-distributions[:,names.index("lacks_pair")]
    assert np.all(np.isfinite(effects))
    contrast=dict(point=summaries["has_pair"]["diff"]-summaries["lacks_pair"]["diff"],
                  ci95=np.quantile(effects,[.025,.975]).tolist(),draws=len(effects))
    save("by-query.json.gz",rows)
    save("results.json",dict(groups=summaries,pair_interaction=contrast,trajectories=len(tids),numpy=np.__version__))
    print(json.dumps({k:(v["n"],v.get("win"),v.get("loss"),v.get("ci95")) for k,v in summaries.items()}))
    print(contrast)

if __name__=="__main__":
    if sys.argv[1]=="lock":
        assert not (ROOT/"lock.json").exists()
        save("lock.json",{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in FILES.items()})
    else:
        analyze()


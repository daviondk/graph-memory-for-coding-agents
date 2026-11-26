"""Replay eager and on-demand validation without exposing unqueried outcomes to the planner."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from lazy import materialize

D=Path(__file__).resolve().parent
W=D.parents[1]
SOURCE=W/"graph_memory_round41"/"structural_invalidation"
GUARD=W/"graph_memory_round40"/"guarded_updates"
sys.path.insert(0,str(W/"graph_memory_round40"/"natural_invalidations"))
from score import select

def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pinned(folder,name):
    assert sha(folder/name)==read(folder/"manifest.json")["files"][name]
    return read(folder/name)

def save(path,data):
    raw=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)

def evaluate():
    assert sha(D/"PROTOCOL_RU.md")=="402104b784bc7065c851308e36bccfee05dcdab7d88367ce566490d172039de7"
    inputs=pinned(GUARD,"selections.json.gz")
    plans=pinned(GUARD,"guarded-plans.json.gz")
    frozen=pinned(SOURCE,"predictions.json.gz")
    out={}
    for e in inputs:
        key=hashlib.sha256((e["run"]+"/"+str(e["receipt"])).encode()).hexdigest()
        base=frozen[key]
        plan=plans[e["run"]][str(e["at"])][0]
        rows=[(i,p,c,u) for i,p,_,_,c,u,_ in plan]
        target={i for i,p,c,u in rows if p==e["path"]}
        geometry={int(i):r for i,r in base["maps"]["range"].items()}
        content={int(i):r for i,r in base["maps"]["content"].items()}
        unresolved=target-set(geometry)
        full={**content,**geometry}
        valid=[r for r in rows if r[0] not in target or r[0] in full]
        canonical=list(select(valid)[0])
        runs={}
        for name,exact in [("boundary",False),("all_completions",True)]:
            found=dict(geometry)
            def lookup(i):
                assert i in unresolved and i not in found
                if i in content:
                    found[i]=content[i]
                return i in found
            ids,asked,packs=materialize(rows,unresolved,lookup,select,1024,exact=exact)
            assert ids==canonical and len(asked)==len(set(asked))
            assert all(found[i]==full[i] for i in ids if i in target)
            runs[name]={"asked":asked,"packs":packs}
        out[key]=dict(issue=e["issue"],held=e["held"],old=base["old"],ids=canonical,
            addresses={str(i):full[i] for i in canonical if i in target},
            uncertain=sorted(unresolved),runs=runs,pair_bytes=base["cost"]["bytes"],
            range_same=base["choices"]["range"]==base["old"],
            content_same=base["choices"]["content"]==base["old"])
    save(D/"forecasts.json.gz",out)
    save(D/"forecast-seal.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),forecast=sha(D/"forecasts.json.gz"),
        programs={n:sha(D/n) for n in ("evaluate.py","lazy.py")},cases=len(out),
        parents={d.name:sha(d/"manifest.json") for d in (GUARD,SOURCE)}))

def summarize(data):
    keys=sorted({e["issue"] for e in data});idx={k:i for i,k in enumerate(keys)}
    counts=np.zeros((len(keys),15),np.int64)
    for e in data:
        eager=len(e["uncertain"]);b=e["runs"]["boundary"];a=e["runs"]["all_completions"]
        g,h=len(b["asked"]),len(a["asked"]);size=e["pair_bytes"]
        counts[idx[e["issue"]]] += (1,eager,g,h,int(eager>0),int(g>0),int(h>0),size*int(eager>0),
            size*int(g>0),size*int(h>0),int(e["ids"]==e["old"]),int(e["range_same"]),int(e["content_same"]),b["packs"],a["packs"])
    titles="events uncertain boundary_queries all_queries eager_files boundary_files all_files eager_bytes boundary_bytes all_bytes union_same range_same content_same boundary_packs all_packs".split()
    rng=np.random.default_rng(420137)
    draws=rng.integers(len(keys),size=(10000,len(keys)))
    metrics={}
    for name,i,j in [("queries_saved",1,3),("pair_reads_saved",4,6),("pair_bytes_saved",7,9),("union_vs_range",10,11),("union_vs_content",10,12),("exact_vs_boundary_queries",2,3)]:
        denom=counts[:,i] if name in ("queries_saved","pair_reads_saved","pair_bytes_saved") else counts[:,0]
        delta=counts[:,i]-counts[:,j]
        drawn=delta[draws].sum(axis=1)/denom[draws].sum(axis=1)
        assert (denom>0).all()
        macro=delta/denom
        metrics[name]=dict(micro=delta.sum()/denom.sum(),ci=np.quantile(drawn,[.025,.975]).tolist(),
            macro=macro.mean(),macro_ci=np.quantile(macro[draws].mean(axis=1),[.025,.975]).tolist())
    return dict(counts=dict(zip(titles,counts.sum(axis=0).tolist())),issues=len(keys),effects=metrics,
        by_issue={k:dict(zip(titles,counts[i].tolist())) for i,k in enumerate(keys)})

if __name__=="__main__":
    evaluate()
    rows=list(read(D/"forecasts.json.gz").values())
    result={k:summarize(v) for k,v in [("held",[r for r in rows if r["held"]]),("all",rows)]}
    save(D/"results.json",result)
    print(result["held"]["counts"])
    print(result["held"]["effects"])

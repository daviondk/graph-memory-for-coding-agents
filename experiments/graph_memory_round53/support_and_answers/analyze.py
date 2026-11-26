"""Decompose paired Answer F1 by the observed change in source-title coverage."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
import gzip
import json
import numpy as np

OUT=Path(__file__).resolve().parent
SOURCE=OUT.parents[1]/"graph_memory_round52"
def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())

def analyze(folder,arms,expected,keys=None,prefix=None):
    source=SOURCE/folder
    paths=[source/name for name in ("records.json.gz","contexts.json.gz")]
    records,contexts=map(read,paths)
    if keys:
        records,contexts=records[keys],contexts[keys]
    ids=sorted(q for q in records if not prefix or q.startswith(prefix))
    assert len(ids)==expected and set(ids)<=set(contexts)
    signs=(-1,0,1)
    counts=np.zeros((3,3),dtype=int);pieces=[];groups=[];rows=[];prompts=Counter()
    for q in ids:
        lhs,rhs=(records[q][a] for a in arms);c=contexts[q]
        if isinstance(lhs,list):
            f1=lhs[0]-rhs[0];full=lhs[2]-rhs[2]
        else:
            f1=lhs["f1"]-rhs["f1"];full=lhs["full"]-rhs["full"]
        l,r=(c["refs"][a] for a in arms)
        assert full in signs and l[2]==r[2]
        same=l[1]==r[1]
        if same:assert abs(f1)<1e-12
        a,b=signs.index(full),int(np.sign(f1))+1
        counts[a,b]+=1
        contribution=[0.,0.,0.];contribution[a]=f1;pieces.append(contribution)
        groups.append(c.get("first",c.get("cluster")))
        prompts["same" if same else "different"]+=1
        rows.append([q,l[0],r[0],full,f1,same])
    pts=np.array(pieces);avg=100*pts.mean(axis=0)
    _,ix=np.unique(groups,return_inverse=True);ns=np.bincount(ix);ng=len(ns)
    by_group=np.stack([np.bincount(ix,weights=pts[:,i]) for i in range(3)],axis=1)
    rng=np.random.default_rng(531233);boots=[]
    for _ in range(100):
        chosen=rng.integers(ng,size=(100,ng));den=ns[chosen].sum(axis=1)
        boots.append(100*by_group[chosen].sum(axis=1)/den[:,None])
    ci=np.quantile(np.vstack(boots),[.025,.975],axis=0)
    return dict(n=len(ids),clusters=ng,arms=arms,same_prompt=prompts["same"],matrix=counts.tolist(),
        signs=list(signs),f1_delta_pp=float(avg.sum()),contribution_pp=avg.tolist(),ci95_pp=ci.T.tolist(),
        hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in paths}),rows

def main():
    results={};receipts={}
    for label,src,arms,n,split,prefix in [
        ("2wiki-dev","global_answers",["primary_href","primary_text"],384,None,None),
        ("2wiki-confirm","global_answers/confirm",["primary_href","primary_text"],512,None,None),
        ("2wiki-fixed-learned","global_answers/confirm/supplement",["learned_href","learned_literal"],512,None,"fallback|"),
        ("hotpot-reranked","reranker",["ce_graph","ce_hybrid"],1280,"hotpot",None),
        ("2wiki-reranked","reranker",["ce_graph","ce_hybrid"],1280,"2wiki",None)]:
        results[label],receipts[label]=analyze(src,arms,n,split,prefix)
    (OUT/"results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n",encoding="utf8")
    (OUT/"rows.json.gz").write_bytes(gzip.compress(json.dumps(receipts,separators=(",",":"),sort_keys=True).encode(),mtime=0))
    for k,v in results.items():print(k, v["matrix"], [round(x,3) for x in v["contribution_pp"]])
if __name__=="__main__":main()


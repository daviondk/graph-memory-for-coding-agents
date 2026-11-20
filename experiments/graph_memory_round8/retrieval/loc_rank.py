"""Full-corpus transfer of the locked policies, no qrels access."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from acquire import ROOT,CACHE,member
from encoder import engine,PREFIX
from prepare import words,digest,SKIP
from pool_rank import bm25
from rank import extract,make_edges,positions,METHODS

TASKS=['cleder__crepr-64','tjorim__pyrail-23','Kuuuube__kanjigrid-11','joselc__life-sim-first-try-2','Happy-Algorithms-League__hal-cgp-180','python-visualization__folium-2003']
def base(t):return 'datasets/loc-bench-function_'+t+'/'
def capture(t,encode):
    q=json.loads(member(base(t)+'queries.jsonl').splitlines()[0])['text']
    assert not SKIP.search(q)
    raw=member(base(t)+'corpus.jsonl')
    corpus={}
    for line in raw.splitlines():
        rec=json.loads(line)
        corpus.setdefault(rec['_id'],rec['text'])
    ids=list(corpus);docs=list(corpus.values());names=[x.rsplit('/',1)[-1] for x in ids]
    b=bm25(docs,set(words(q)))
    br=positions(b,ids)
    qv=encode([PREFIX+q])[0]
    store=CACHE/'loc-raw-embeddings';store.mkdir(exist_ok=True)
    paths=[store/(digest(doc)+'.npy') for doc in docs]
    ordered=sorted((i for i in range(len(ids)) if not paths[i].exists()),key=lambda i:len(docs[i]))
    for start in range(0,len(ordered),4):
        group=ordered[start:start+4]
        for i,vector in zip(group,encode([docs[i] for i in group])): np.save(paths[i],vector)
    vs=[np.load(p) for p in paths]
    dot=[float(qv@v) for v in vs]
    dense=[float(s/(np.linalg.norm(qv)*np.linalg.norm(v))) for s,v in zip(dot,vs)]
    dr=positions(dense,ids)
    fused=[1/(10+x)+1/(10+y) for x,y in zip(dr,br)]
    explicit=extract(q)
    hits=sorted((i for i,n in enumerate(names) if n in explicit),key=lambda i:(-explicit[names[i]],br[i]))[:8]
    anchor={a:1/(10+k) for k,a in enumerate(hits,1)}
    direct=[s+anchor.get(i,0) for i,s in enumerate(fused)]
    # Sort graph permutation by BM25 order first, matching the primary panel's input ordering.
    bmorder=sorted(range(len(ids)),key=lambda j:br[j])
    shuffled=sorted(range(len(ids)),key=lambda j:digest(t+'|'+ids[j]))
    permutation=dict(zip(bmorder,shuffled))
    edges=make_edges(docs,names)
    def expand(es):
        extra=[0.0]*len(ids)
        for a,b in es:
            for x,y in ((a,b),(b,a)):
                if x in anchor and y not in anchor:extra[y]=max(extra[y],.5*anchor[x])
        return [a+b for a,b in zip(direct,extra)]
    data=dict(bm25=b,dense=dense,dense_dot=dot,rrf=fused,direct=direct,graph=expand(edges),rewired=expand([(permutation[i],permutation[j]) for i,j in edges]))
    ranks={m:positions(v,ids) for m,v in data.items()}
    result=dict(task=t,repo=t.rsplit('-',1)[0],n_corpus=len(ids),corpus_sha256=hashlib.sha256(raw).hexdigest(),query_sha256=digest(q),anchors=[ids[i] for i in hits],edges=[[ids[a],ids[b]] for a,b in edges],explicit_identifiers=explicit,candidates=[dict(id=ident,scores={m:data[m][i] for m in METHODS},ranks={m:ranks[m][i] for m in METHODS}) for i,ident in enumerate(ids)])
    return result
if __name__=='__main__':
    assert not (ROOT/'loc_seal.json').exists()
    encode=engine()
    out=ROOT/'loc_predictions';out.mkdir(exist_ok=True)
    for t in TASKS:
        start=time.monotonic()
        path=out/(t+'.json')
        if not path.exists():path.write_text(json.dumps(capture(t,encode),indent=1),encoding='utf8')
        print(t,round(time.monotonic()-start,1),flush=True)
    files=[ROOT/f for f in ['loc_protocol.md','loc_rank.py','loc_score.py','acquire.py','prepare.py','rank.py','pool_rank.py','encoder.py','model_manifest.json','backend_manifest.json']]+list(out.glob('*.json'))
    assert len(list(out.glob('*.json')))==len(TASKS)
    (ROOT/'loc_seal.json').write_text(json.dumps({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))

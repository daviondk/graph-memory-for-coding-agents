"""Blind predictions. This file never opens or parses judgments."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import time
import numpy as np

from acquire import ROOT,CACHE
from encoder import PREFIX,engine
from prepare import digest

IDENT=r'[A-Za-z_][A-Za-z_0-9]*'
CALL=re.compile(r'\b('+IDENT+r')\s*\(')
SEQ=re.compile(r'\b'+IDENT+r'\b')
METHODS=['bm25','dense','rrf','direct','graph','rewired','dense_dot']
def positions(scores,ids):
    ix=sorted(range(len(ids)),key=lambda i:(-scores[i],ids[i]))
    ranks=[0]*len(ix)
    for rank,i in enumerate(ix,1): ranks[i]=rank
    return ranks
def extract(query):
    tokens=SEQ.findall(query)
    codes=set(CALL.findall(query))
    codes.update(t for t in tokens if '_' in t or (not t.islower() and not t.isupper() and any(c.isupper() for c in t[1:])))
    for fragment in re.findall(r'\x60{1,2}([^\x60\n]{1,100})\x60{1,2}',query):
        codes.update(SEQ.findall(fragment))
    return {t:n for t,n in Counter(tokens).items() if t in codes and len(t)>=3}
def make_edges(docs,names):
    by_name=defaultdict(list)
    for i,n in enumerate(names): by_name[n].append(i)
    edges=set()
    for i,d in enumerate(docs):
        lines=[l for l in d.splitlines()[1:] if not re.match(r'^\s*(?:async\s+)?def\s+',l)]
        for call in set(CALL.findall('\n'.join(lines))):
            hit=by_name.get(call,[])
            if len(hit)==1 and hit[0]!=i: edges.add(tuple(sorted((i,hit[0]))))
    return sorted(edges)
def run(task,encode):
    d=json.loads((CACHE/'shortlists'/(task+'.json')).read_text(encoding='utf-8'))
    rows=d.pop('candidates')
    docs=[r['text'] for r in rows]
    ids=[r['id'] for r in rows]
    assert len(set(ids))==len(ids)==40
    q=d.pop('query')
    qv=encode([PREFIX+q])[0]
    vd=CACHE/'raw-embeddings-fp32-1024';vd.mkdir(exist_ok=True)
    paths=[vd/(digest(body)+'.npy') for body in docs]
    todo=sorted((i for i in range(len(docs)) if not paths[i].exists()),key=lambda i:len(docs[i]))
    for k in range(0,len(todo),4):
        group=todo[k:k+4]
        for i,x in zip(group,encode([docs[i] for i in group])):
            np.save(paths[i],x)
    vectors=[np.load(p) for p in paths]
    dots=[float(np.dot(qv,v)) for v in vectors]
    dense=[float(s/(np.linalg.norm(qv)*np.linalg.norm(v))) for s,v in zip(dots,vectors)]
    densepos=positions(dense,ids)
    bm25=[r['bm25'] for r in rows]; bmpos=positions(bm25,ids)
    rrf=[1/(10+a)+1/(10+b) for a,b in zip(densepos,bmpos)]
    names=[x.rsplit('/',1)[-1] for x in ids]; evidence=extract(q)
    hits=sorted((i for i,s in enumerate(names) if s in evidence),key=lambda i:(-evidence[names[i]],bmpos[i]))[:8]
    signal={i:1/(10+k) for k,i in enumerate(hits,1)}
    direct=[s+signal.get(i,0) for i,s in enumerate(rrf)]
    edges=make_edges(docs,names)
    pi=sorted(range(len(ids)),key=lambda i:digest(task+'|'+ids[i]))
    perm_edges=[(pi[a],pi[b]) for a,b in edges]
    def propagate(es):
        result=[0.0]*len(ids)
        for x,y in es:
            for a,b in [(x,y),(y,x)]:
                if a in signal and b not in signal: result[b]=max(result[b],.5*signal[a])
        return [a+b for a,b in zip(direct,result)]
    graph,rewired=propagate(edges),propagate(perm_edges)
    scores=dict(zip(METHODS,[bm25,dense,rrf,direct,graph,rewired,dots]))
    ranks={model:positions(s,ids) for model,s in scores.items()}
    d.update(anchors=[ids[i] for i in hits],edges=[[ids[i],ids[j]] for i,j in edges],explicit_identifiers=evidence,candidates=[dict(id=ids[i],scores={m:float(scores[m][i]) for m in METHODS},ranks={m:ranks[m][i] for m in METHODS}) for i in range(len(ids))])
    return d
if __name__=='__main__':
    sample=json.loads((ROOT/'sample.json').read_text())['selected']
    assert not (ROOT/'seal.json').exists(), 'Start from an empty predictions directory for new runs'
    t=time.monotonic()
    encode=engine()
    out=ROOT/'predictions';out.mkdir(exist_ok=True)
    for task in sample:
        file=out/(task+'.json')
        start=time.monotonic()
        if not file.exists():
            result=run(task,encode)
            tmp=file.with_suffix('.tmp')
            tmp.write_text(json.dumps(result,ensure_ascii=False,indent=1),encoding='utf-8')
            tmp.replace(file)
        print(task,round(time.monotonic()-start,1),'s',flush=True)
    inputs=[ROOT/x for x in ['prelabel_amendment.md','sample.json','protocol.md','encoder.py','prepare.py','rank.py','acquire.py','backend_manifest.json','model_manifest.json']]
    files=inputs+list(out.glob('*.json'))
    assert len(list(out.glob('*.json')))==len(sample)
    manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (ROOT/'seal.json').write_text(json.dumps(manifest,indent=2))
    print('sealed',round(time.monotonic()-t,1),'seconds',flush=True)

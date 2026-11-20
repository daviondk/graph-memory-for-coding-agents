"""Degree-aware allocation on fresh complete SWE function corpora."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from acquire import ROOT,index,member
from prepare import digest,prefix,get_task,words,REPOS,SKIP
from pool_rank import bm25,calls
from rank import extract,positions

METHODS=['body','field','direct','uniform','gate','allocation']
def choose():
    used=set(json.loads((ROOT/'pool_sample.json').read_text()))|set(json.loads((ROOT/'sample.json').read_text())['selected'])
    ids0=[k.split('swe-bench-lite-function_')[1].split('/')[0] for k in index() if k.startswith('datasets/swe-bench-lite-function_') and k.endswith('/queries.jsonl')]
    selected=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for repo in REPOS:
            ids=sorted([i for i in ids0 if i.rsplit('-',1)[0]==repo and i not in used],key=lambda t:digest('R8-lookup-v1|'+t))[:6]
            selected.extend([t for t,q in zip(ids,pool.map(get_task,ids)) if not SKIP.search(q)][:4])
    assert not used.intersection(selected)
    return selected
def rank(t):
    q=get_task(t); raw=member(prefix(t)+'corpus.jsonl');corpus={}
    for line in raw.splitlines():
        d=json.loads(line);corpus.setdefault(d['_id'],d['text'])
    ids=list(corpus);docs=list(corpus.values());names=[i.rsplit('/',1)[-1] for i in ids]
    terms=set(words(q));ls=bm25(docs,terms);ads=bm25(ids,terms)
    lr=positions(ls,ids);ar=positions(ads,ids)
    field=[1/(10+x)+(1/(10+y) if s>0 else 0) for x,y,s in zip(lr,ar,ads)]
    explicit=extract(q)
    anchors=sorted((i for i,n in enumerate(names) if n in explicit),key=lambda i:(-explicit[names[i]],lr[i]))[:8]
    weight={a:1/(10+k) for k,a in enumerate(anchors,1)}
    direct=[f+weight.get(i,0) for i,f in enumerate(field)]
    counts=Counter(names);unique={n:i for i,n in enumerate(names) if counts[n]==1}
    a_by_name={names[a]:a for a in anchors if counts[names[a]]==1}
    neighbors=defaultdict(set)
    if anchors:
        for i,doc in enumerate(docs):
            invoke=calls(doc)
            if i not in weight:
                for n in invoke & a_by_name.keys():neighbors[a_by_name[n]].add(i)
            if i in weight:
                neighbors[i].update(unique[n] for n in invoke if n in unique and unique[n] not in weight)
    sup=defaultdict(list)
    for a,ns in neighbors.items():
        for n in ns:sup[n].append(a)
    scores={'body':ls,'field':field,'direct':direct}
    for mode in ['uniform','gate','allocation']:
        b=direct.copy()
        for n,aa in sup.items():
            bonus=max((weight[a]/(len(neighbors[a]) if mode=='allocation' else 1) for a in aa if mode!='gate' or len(neighbors[a])<=40),default=0)
            b[n]+=.5*bonus
        scores[mode]=b
    top={}
    for m,ss in scores.items():
        hit=sorted(range(len(ids)),key=lambda i:(-ss[i],ids[i]))[:40]
        top[m]=[{'id':ids[i],'score':ss[i],'supports':[ids[a] for a in sorted(sup.get(i,[]))]} for i in hit]
    return {'task':t,'repo':t.rsplit('-',1)[0],'query_sha256':digest(q),'corpus_sha256':hashlib.sha256(raw).hexdigest(),'n_corpus':len(ids),'n_scanned_for_graph':len(ids) if anchors else 0,'n_propagated':len(sup),'anchors':[ids[a] for a in anchors],'degrees':{ids[a]:len(neighbors[a]) for a in anchors},'top40':top}
if __name__=='__main__':
    out=ROOT/'degree_predictions';out.mkdir(exist_ok=True)
    selected=choose();(ROOT/'degree_sample.json').write_text(json.dumps(selected,indent=2))
    for t in selected:
        (out/(t+'.json')).write_text(json.dumps(rank(t),indent=1))
        print(t,flush=True)
    files=[ROOT/f for f in ['degree_protocol.md','degree_rank.py','degree_score.py','degree_sample.json','pool_rank.py','rank.py','prepare.py','acquire.py']]+list(out.glob('*.json'))
    (ROOT/'degree_seal.json').write_text(json.dumps({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))

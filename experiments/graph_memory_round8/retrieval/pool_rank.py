"""Independent disjoint full-corpus candidate-generation ablation."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import re
import time
from acquire import ROOT,index,member
from prepare import REPOS,SKIP,digest,prefix,get_task,words
from rank import CALL,extract,positions

METHODS=['body','field','direct','graph']
def choose():
    known=set(json.loads((ROOT/'sample.json').read_text())['selected'])
    dirs=index()
    selected=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for repo in REPOS:
            ids=[x.split('swe-bench-lite-function_')[1].split('/')[0] for x in dirs if x.startswith('datasets/swe-bench-lite-function_'+repo+'-') and x.endswith('/queries.jsonl')]
            ids=sorted((x for x in ids if x not in known),key=lambda x:digest('R8-lookup-v1|'+x))[:9]
            new=[i for i,q in zip(ids,pool.map(get_task,ids)) if not SKIP.search(q)][:6]
            assert len(new)==6
            selected.extend(new)
    assert not known.intersection(selected)
    return selected
def bm25(strings,terms):
    hits=[];lengths=[];df=Counter()
    for body in strings:
        n=0; hit=Counter()
        for w in words(body):
            n+=1
            if w in terms: hit[w]+=1
        lengths.append(n);hits.append(hit);df.update(hit.keys())
    N=len(strings);avg=sum(lengths)/N
    idf={w:math.log1p((N-k+.5)/(k+.5)) for w,k in df.items()}
    return [sum(idf[w]*2.2*f/(f+1.2*(.25+.75*length/avg)) for w,f in hit.items()) for length,hit in zip(lengths,hits)]
def calls(doc):
    return set(CALL.findall('\n'.join(l for l in doc.splitlines()[1:] if not re.match(r'^\s*(?:async\s+)?def\s+',l))))
def process(task):
    query=get_task(task)
    raw=member(prefix(task)+'corpus.jsonl')
    corpus={}
    for line in raw.splitlines():
        d=json.loads(line)
        corpus.setdefault(d['_id'],d['text'])
    ids=list(corpus);bodies=list(corpus.values());names=[w.rsplit('/',1)[-1] for w in ids]
    qterms=set(words(query))
    lex=bm25(bodies,qterms); address=bm25(ids,qterms)
    lr=positions(lex,ids);ar=positions(address,ids)
    field=[1/(10+b)+(1/(10+a) if s>0 else 0) for b,a,s in zip(lr,ar,address)]
    explicit=extract(query)
    anchors=sorted((i for i,n in enumerate(names) if n in explicit),key=lambda i:(-explicit[names[i]],lr[i]))[:8]
    lookup=Counter(names); pos={name:i for i,name in enumerate(names) if lookup[name]==1}
    value={a:1/(10+k) for k,a in enumerate(anchors,1)}
    direct=[b+value.get(i,0) for i,b in enumerate(field)]
    support=defaultdict(set)
    if anchors:
        anchor_names={names[a]:a for a in anchors if lookup[names[a]]==1}
        for i,body in enumerate(bodies):
            invoked=calls(body)
            for n in anchor_names.keys() & invoked:
                if i not in value: support[i].add(anchor_names[n])
            if i in value:
                for n in invoked:
                    if n in pos and pos[n] not in value: support[pos[n]].add(i)
    graph=[s+.5*max((value[a] for a in support.get(i,[])),default=0) for i,s in enumerate(direct)]
    model_scores=dict(zip(METHODS,[lex,field,direct,graph]))
    results=dict(task=task,repo=task.rsplit('-',1)[0],corpus_sha256=hashlib.sha256(raw).hexdigest(),query_sha256=digest(query),n_corpus=len(ids),n_scanned_for_graph=len(ids) if anchors else 0,n_propagated=len(support),anchors=[ids[i] for i in anchors],top40={})
    for m,sc in model_scores.items():
        top=sorted(range(len(ids)),key=lambda i:(-sc[i],ids[i]))[:40]
        results['top40'][m]=[{'id':ids[i],'score':sc[i],'supports':[ids[a] for a in sorted(support.get(i,[]))]} for i in top]
    path=ROOT/'pool_predictions'/(task+'.json')
    path.write_text(json.dumps(results,indent=1),encoding='utf8')
    print(task,results['n_corpus'],flush=True)
if __name__=='__main__':
    assert not (ROOT/'pool_seal.json').exists()
    selected=choose()
    (ROOT/'pool_sample.json').write_text(json.dumps(selected,indent=2))
    (ROOT/'pool_predictions').mkdir(exist_ok=True)
    for t in selected:process(t)
    paths=[ROOT/'pool_protocol.md',ROOT/'pool_rank.py',ROOT/'pool_sample.json',ROOT/'pool_score.py',ROOT/'acquire.py',ROOT/'rank.py',ROOT/'prepare.py']+list((ROOT/'pool_predictions').glob('*.json'))
    (ROOT/'pool_seal.json').write_text(json.dumps({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2))

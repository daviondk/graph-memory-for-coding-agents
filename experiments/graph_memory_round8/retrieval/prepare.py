"""Select tasks and make an unjudged, label-independent shortlist."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import re

from acquire import ROOT,CACHE,index,member

REPOS=['sympy__sympy','sphinx-doc__sphinx','matplotlib__matplotlib']
SKIP=re.compile(r'\b(?:CVE|exploit|vulnerabilit(?:y|ies)|arbitrary code execution|security|injection|denial of service)\b',re.I)
LEX=re.compile(r'[A-Za-z][A-Za-z0-9_]+')
CAMEL=re.compile(r'[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|[A-Z]|\d+')
def words(s):
    for w in LEX.findall(s):
        whole=w.lower()
        yield whole
        for part in CAMEL.findall(w):
            if len(part)>1 and part.lower()!=whole: yield part.lower()
def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
def prefix(task): return 'datasets/swe-bench-lite-function_'+task+'/'
def get_task(task):
    base=prefix(task)
    qdata=member(base+'queries.jsonl')
    q=json.loads(qdata.splitlines()[0])
    assert q['_id']==task
    return q['text']
def select():
    folders=index()
    tasks=[p.split('swe-bench-lite-function_')[1].split('/')[0] for p in folders if p.startswith('datasets/swe-bench-lite-function_') and p.endswith('/queries.jsonl')]
    exclusions=[]
    selected=[]
    with ThreadPoolExecutor(max_workers=10) as pool:
        for repo in REPOS:
            group=sorted((t for t in tasks if t.rsplit('-',1)[0]==repo),key=lambda s:digest('R8-lookup-v1|'+s))
            for task,q in zip(group,pool.map(get_task,group[:9])):
                if SKIP.search(q): exclusions.append(task); continue
                selected.append(task)
                if sum(s.rsplit('-',1)[0]==repo for s in selected)==6: break
            assert sum(s.rsplit('-',1)[0]==repo for s in selected)==6
    return selected,exclusions
def shortlist(task):
    query=get_task(task)
    raw=member(prefix(task)+'corpus.jsonl')
    qterms=set(words(query))
    found=[]
    document_frequency=Counter()
    ids=set()
    for s in raw.splitlines():
        d=json.loads(s)
        ident=d['_id']
        if ident in ids: continue
        ids.add(ident)
        lengths=0
        terms=Counter()
        for term in words(d['text']):
            lengths+=1
            if term in qterms: terms[term]+=1
        document_frequency.update(terms.keys())
        found.append([ident,lengths,terms,d['text']])
    N=len(found)
    avg=sum(d[1] for d in found)/N
    idf={w:math.log1p((N-n+.5)/(n+.5)) for w,n in document_frequency.items()}
    candidates=[]
    for ident,length,terms,txt in found:
        bias=1.2*(.25+.75*length/avg)
        score=sum(idf[w]*(2.2*tf)/(tf+bias) for w,tf in terms.items())
        candidates.append({'id':ident,'bm25':score,'text':txt})
    candidates.sort(key=lambda x:(-x['bm25'],x['id']))
    result={'task':task,'repo':task.rsplit('-',1)[0],'query':query,'corpus_sha256':hashlib.sha256(raw).hexdigest(),'query_sha256':digest(query),'n_corpus':N,'candidates':candidates[:40]}
    p=CACHE/'shortlists';p.mkdir(exist_ok=True)
    (p/(task+'.json')).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print(task,N,flush=True)
if __name__=='__main__':
    selected,excluded=select()
    (ROOT/'sample.json').write_text(json.dumps({'selected':selected,'excluded':excluded,'protocol_sha256':hashlib.sha256((ROOT/'protocol.md').read_bytes()).hexdigest()},indent=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(shortlist,selected))

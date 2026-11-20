"""Blind first-stage scores on the whole candidate corpus for each released issue."""
import json,time
from pathlib import Path
import numpy as np
from source import ROOT,R8,CACHE,h,inputs,base,member,load_json,write_json,MODEL_SHAS
from encoder import engine,PREFIX,BACKEND
from pool_rank import bm25
from prepare import words
def run(t,encode):
    query,qsha=inputs(t)
    raw=member(base(t)+'corpus.jsonl')
    rows=[json.loads(x) for x in raw.splitlines()]
    ids=[d['_id'] for d in rows]; ss=[d['text'] for d in rows]
    assert len(ids)==len(set(ids))
    qv=encode([PREFIX+query])[0]
    lexical=bm25(ss,set(words(query)))
    # Use strict text hashes; embeddings shared if and only if the complete official corpus representation matches.
    cache=CACHE/'r9-raw-vectors';cache.mkdir(exist_ok=True)
    old=[CACHE/'loc-raw-embeddings',CACHE/'raw-embeddings-fp32-1024']
    def get_path(txt):
        name=h(txt)+'.npy'
        for where in old:
            if (where/name).exists():return where/name
        return cache/name
    paths=[get_path(txt) for txt in ss]
    todo=sorted((i for i,p in enumerate(paths) if not p.exists()),key=lambda i:len(ss[i]))
    elapsed=time.monotonic()
    for j in range(0,len(todo),4):
        ix=todo[j:j+4]
        for i,v in zip(ix,encode([ss[k] for k in ix])):np.save(paths[i],v)
    dense=[float(qv@np.load(p)) for p in paths]
    return {'issue':t,'timing_s':time.monotonic()-elapsed,'from_embedding_cache':len(ids)-len(todo),'corpus_sha256':h(raw),'query_file_sha256':qsha,'candidates':[{'id':i,'dot':d,'bm25':b} for i,d,b in zip(ids,dense,lexical)]}
if __name__=='__main__':
    sample=load_json(ROOT/'sample.json')['selected']
    assert all(h((CACHE/'model'/f).read_bytes())==sha for f,sha in MODEL_SHAS.items())
    encode=engine()
    out=ROOT/'dense';out.mkdir(exist_ok=True)
    for row in sample:
        t=row['issue'];p=out/(t+'.json')
        if p.exists():continue
        record=run(t,encode)
        assert record['corpus_sha256']==row['corpus_sha256'] and len(record['candidates'])==row['functions']
        tmp=p.with_suffix('.tmp');write_json(tmp,record);tmp.replace(p)
        print(t,len(record['candidates']),round(record['timing_s'],1),flush=True)

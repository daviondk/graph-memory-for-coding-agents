"""Prepare the immutable shared store and opaque worker packets. Never copies raw documents into the report."""
import csv
import json
import sqlite3
from pathlib import Path
from urllib.request import urlretrieve
import numpy as np

from prepare import CACHE, MODEL, ROOT, cid, dump, encode, sha

RAG_URL='https://huggingface.co/datasets/ofai/RagabilityCorpus/resolve/2251634ed365bfca55e7d808290b0cf2c5fde730/Dataset_v0.4.tsv'
RAG_HASH='e973f5ac7b4881e2cafe23f39b837643878ea6afdb769d9afa30ff66e93c8285'


def rag_packets():
    src=CACHE/'rag.tsv'
    if not src.exists():
        urlretrieve(RAG_URL,src)
    assert sha(src.read_bytes())==RAG_HASH
    with src.open(encoding='utf8',newline='') as f:
        rows=list(csv.DictReader(f,delimiter='\t'))
    keys=('context_1','context_2','context_3_nc1_c2','context_4_nc1_nc2_nc3')
    texts={cid(r[k].strip()):r[k].strip() for r in rows for k in keys}
    ids=sorted(texts)
    sentences=['passage: '+texts[h] for h in ids]+['query: '+r['query_text'].strip() for r in rows]
    vec_file=CACHE/'rag-vectors-v1.npy'
    mat=np.load(vec_file) if vec_file.exists() else encode(sentences,MODEL,vec_file)
    assert mat.shape==(len(sentences),768)
    p=mat[:len(ids)]
    qcos=mat[len(ids):] @ p.T
    rp=np.random.default_rng(2107).standard_normal((768,128)).astype(np.float32)
    sig=np.packbits(((p-p.mean(axis=0))@rp)>0,axis=1)
    packets=[]; gold=[]
    for i,r in enumerate(rows):
        # Keep material unlabelled in the predictor and apply eligibility only in the evaluator.
        name=f'r{i:03}'
        h=[cid(r[k].strip()) for k in keys]
        side=int(cid('distractor-side'+name),16)%2
        groups=[]
        for j,other in [(0,2+side),(1,3-side)]:
            ordered=sorted([h[j],h[other]],key=lambda v:cid('slot'+v+name))
            groups.append([dict(id=v,text=texts[v],cos=int(np.clip(np.rint(qcos[i,ids.index(v)]*32767),-32768,32767)),sketch=sig[ids.index(v)].tobytes().hex()) for v in ordered])
        packets.append(dict(case=name,workers=groups))
        gold.append(dict(case=name,article=r['contradiction_ID'].strip(),eligible=len(set(h))==4 and all(r[k].strip().lower()!='qn' for k in ('c1xq','c2xq')),pair=[h[0],h[1]],alternative=[h[2],h[1]],template=r['WikiContradict_ID'].strip()))
    dump(CACHE/'rag-gold.json',gold)
    return packets


def build(source, cases):
    path=CACHE/f'{source}-refs.sqlite'
    db=sqlite3.connect(path)
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS evidence (id BLOB PRIMARY KEY, n INTEGER NOT NULL, sketch BLOB NOT NULL, body BLOB NOT NULL) WITHOUT ROWID')
        seen={}
        workers=[]
        for r in cases:
            sanitized=[]
            for group in r['workers']:
                ranked=sorted(enumerate(group), key=lambda x:(-x[1]['cos'],x[0]))
                sanitized.append([v['id'] for _,v in ranked])
                for c in group:
                    body=c['text'].encode()
                    assert cid(c['text'])==c['id']
                    rec=(bytes.fromhex(c['id']),len(body),bytes.fromhex(c['sketch']),body)
                    assert seen.setdefault(rec[0], rec)==rec
            workers.append(dict(case=r['case'],workers=sanitized))
        db.executemany('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?)',seen.values())
        assert sorted(db.execute('SELECT id,n,sketch,body FROM evidence'))==sorted(seen.values())
    n=len(seen)
    payload=sum(c[1] for c in seen.values())
    db.close()
    dump(CACHE/f'{source}-workers.json',workers)
    return dict(documents=n,payload_utf8=payload,physical_db_bytes=path.stat().st_size,logical_body_meta_bytes=payload+26*n,ingest_wire_bytes_if_one_remote_row=payload+(3+8+2+16+3)*n,worker_packets=sha((CACHE/f'{source}-workers.json').read_bytes()),db_sha=sha(path.read_bytes()))


if __name__=='__main__':
    wiki=json.loads((CACHE/'packets.json').read_text(encoding='utf8'))
    rag=rag_packets()
    stats={s:build(s,x) for s,x in [('wiki',wiki),('rag',rag)]}
    stats['evaluator_sha']={s:sha((CACHE/g).read_bytes()) for s,g in [('wiki','gold.json'),('rag','rag-gold.json')]}
    stats['rag_sha']=RAG_HASH
    dump(ROOT/'pointer-input-lock.json',stats)


"""Blind payload selection; this program never opens reference labels or the source CSV."""
import argparse
import gzip
import hashlib
import json
import random
import struct
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
METHODS=('bm25','dense','dense_with_synopsis','shuffled','paired')
BUDGETS=(768,1536,3072)


def sha(x):
    return hashlib.sha256(x).hexdigest()


def midrank_percentile(x):
    a=np.asarray(x)
    flat=a.ravel()
    distinct,inv,count=np.unique(flat,return_inverse=True,return_counts=True)
    low=np.cumsum(count)-count
    return ((low[inv]+(count[inv]-1)/2)/max(1,len(flat)-1)).reshape(a.shape)


def descriptors(workers):
    return [b''.join(struct.pack('>h16s',c['cos'],bytes.fromhex(c['sketch'])) for c in group) for group in workers]


def nominate(messages, method, case):
    rows=[list(struct.iter_unpack('>h16s',m)) for m in messages]
    scores=[midrank_percentile([c[0] for c in r]) for r in rows]
    unary=scores[0][:,None]+scores[1][None,:]
    if method=='dense_with_synopsis':
        utility=unary
    else:
        sketches=[[int.from_bytes(c[1], 'big') for c in r] for r in rows]
        if method=='shuffled':
            for i, side in enumerate(sketches):
                random.Random(sha(f'sham:{case}:{i}'.encode())).shuffle(side)
        similarity=np.asarray([[128-(a^b).bit_count() for b in sketches[1]] for a in sketches[0]])
        utility=unary+midrank_percentile(similarity)
    return np.unravel_index(np.argmax(utility),utility.shape)


def pack(worker, method, choice, max_bytes, slots):
    scores='bm' if method=='bm25' else 'cos'
    ranked=sorted(range(len(worker)),key=lambda i:(-worker[i][scores],i))
    if choice is not None:
        ranked.remove(choice)
        ranked.insert(0,choice)
    body=bytearray()
    kept=[]
    for i in ranked:
        c=worker[i]
        txt=c['text'].encode()
        frame=bytes.fromhex(c['id'])+struct.pack('>H',len(txt))+txt
        if len(frame)+len(body)<=max_bytes:
            body.extend(frame)
            kept.append(c['id'])
            if slots==1:
                break
    # Verify the actual wire framing; never emit the contents into public logs.
    offset=0
    decoded=[]
    while offset<len(body):
        h=bytes(body[offset:offset+8]).hex()
        n=struct.unpack_from('>H',body,offset+8)[0]
        assert sha(body[offset+10:offset+10+n])[:16]==h
        decoded.append(h)
        offset+=10+n
    assert offset==len(body) and decoded==kept
    return bytes(body),kept


def forecast(packets, destination):
    rows=[]
    for episode in packets:
        groups=episode['workers']
        case=episode['case']
        for method in METHODS:
            with_synopsis=method in ('paired','shuffled','dense_with_synopsis')
            syn=descriptors(groups) if with_synopsis else [b'',b'']
            choices=nominate(syn,method,case) if with_synopsis else (None,None)
            requests=[bytes([v]) for v in choices] if with_synopsis else [b'',b'']
            overhead=sum(map(len,syn+requests))
            assert overhead==(218 if with_synopsis else 0)
            for budget in BUDGETS:
                for limit in ('fill','one'):
                    quota=(budget-overhead)//2
                    blobs=[]
                    kept=[]
                    for g,k in zip(groups,choices):
                        b,ids=pack(g,method,k,quota,1 if limit=='one' else 0)
                        blobs.append(b)
                        kept.append(ids)
                    used=overhead+sum(map(len,blobs))
                    assert used<=budget
                    rows.append(dict(case=case,method=method,budget=budget,limit=limit,used=used,overhead=overhead,chosen=[None if k is None else int(k) for k in choices],ids=kept,wire_hash=sha(b''.join(syn+requests+blobs))))
    with destination.open('wb') as out, gzip.GzipFile(fileobj=out,mode='wb',filename='',mtime=0) as z:
        for row in rows:
            z.write((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode())
    return len(rows)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--packets',type=Path,default=Path('D:/CodexResearch/x20-wikicontradict/packets.json'))
    a=p.parse_args()
    lock=json.loads((ROOT/'input-lock.json').read_text())
    assert sha(a.packets.read_bytes())==lock['packets_sha']
    dest=ROOT/'forecasts.jsonl.gz'
    count=forecast(json.loads(a.packets.read_text(encoding='utf-8')),dest)
    lock=dict(count=count,forecast=sha(dest.read_bytes()),protocol=sha((ROOT/'protocol.json').read_bytes()),selector=sha(Path(__file__).read_bytes()),packets=lock['packets_sha'])
    (ROOT/'forecast-lock.json').write_text(json.dumps(lock,sort_keys=True,indent=2)+'\n',encoding='utf-8')


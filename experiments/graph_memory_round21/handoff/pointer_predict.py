"""Reference protocol. All application messages traverse a real local socketpair, with byte checks."""
import gzip
import hashlib
import json
import random
import socket
import sqlite3
import struct
from collections import Counter
from pathlib import Path
import numpy as np

from predict import midrank_percentile

ROOT=Path(__file__).resolve().parent
CACHE=Path('D:/CodexResearch/x20-wikicontradict')
METHODS=('length_e5','schema_e5','paired','shuffled')
BUDGETS={'wiki':[768,1536,3072],'rag':[256,512,1024,1536]}


def h(b):
    return hashlib.sha256(b).hexdigest()


def frame(tag,payload):
    return struct.pack('>cH',tag,len(payload))+payload


def readn(sock,n):
    data=bytearray()
    while len(data)<n:
        part=sock.recv(n-len(data))
        if not part: raise EOFError('truncated frame')
        data.extend(part)
    return bytes(data)


class Link:
    def __init__(self):
        self.left,self.right=socket.socketpair()
        if self.left.family in (socket.AF_INET,socket.AF_INET6):
            for sock in (self.left,self.right):
                sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)

    def reset(self):
        self.cost=Counter()
        self.digest=hashlib.sha256()

    def message(self,tag,payload,direction):
        a,b=(self.left,self.right) if direction=='request' else (self.right,self.left)
        data=frame(tag,payload)
        a.sendall(data)
        header=readn(b,3)
        actual_tag,size=struct.unpack('>cH',header)
        result=readn(b,size)
        assert actual_tag==tag and header+result==data
        self.cost[tag.decode()]+=len(data)
        self.digest.update(data)
        return result

    def close(self):
        self.left.close(); self.right.close()


def run(case,workers,db,wire,policy,budget,one):
    wire.reset()
    ids=[]
    for local in workers:
        assert not wire.message(b'R',b'','request')
        body=wire.message(b'I',b''.join(bytes.fromhex(x) for x in local[:2]),'response')
        assert len(body)==16
        ids.append([body[:8],body[8:]])
    catalog=wire.message(b'L' if policy=='length_e5' else b'S',b''.join(v for row in ids for v in row),'request')
    offer=bytearray()
    for i in range(0,len(catalog),8):
        if policy=='length_e5':
            (n,)=db.execute('SELECT n FROM evidence WHERE id=?',(catalog[i:i+8],)).fetchone()
            offer.extend(struct.pack('>H',n))
        else:
            n,sig=db.execute('SELECT n,sketch FROM evidence WHERE id=?',(catalog[i:i+8],)).fetchone()
            offer.extend(struct.pack('>H16s',n,sig))
    payload=wire.message(b'M',bytes(offer),'response')
    entries=list(struct.iter_unpack('>H' if policy=='length_e5' else '>H16s',payload))
    sizes=[r[0] for r in entries]
    best=(0,0)
    if policy in ('paired','shuffled'):
        sketches=[[int.from_bytes(x[1],'big') for x in entries[i:i+2]] for i in (0,2)]
        if policy=='shuffled':
            for i,g in enumerate(sketches):
                random.Random(h(f'sham:{case}:{i}'.encode())).shuffle(g)
        associates=np.array([[128-(a^b).bit_count() for b in sketches[1]] for a in sketches[0]])
        # Give mean local relevance and cross-worker association equal scale.
        # Ties retain the earlier local candidate.
        priority=np.asarray([1.,0.])
        combined=(priority[:,None]+priority[None,:])/2+midrank_percentile(associates)
        best=np.unravel_index(np.argmax(combined),combined.shape)
    idx=[int(best[0]),int(best[1])+2,1-int(best[0]),3-int(best[1])]
    costs=[24+n for n in sizes] # G(3+8 bytes), V(3+8+2+n bytes)
    kept=[[],[]]
    initial=sum(wire.cost.values())
    assert initial==(90 if policy=='length_e5' else 154), (initial,policy)
    pair_fits=initial+costs[idx[0]]+costs[idx[1]]<=budget
    for i in idx:
        worker=i//2
        if one and kept[worker]: continue
        if sum(wire.cost.values())+costs[i]>budget: continue
        key=wire.message(b'G',ids[worker][i%2],'request')
        (txt,)=db.execute('SELECT body FROM evidence WHERE id=?',(key,)).fetchone()
        body=wire.message(b'V',key+struct.pack('>H',len(txt))+txt,'response')
        n=struct.unpack('>H',body[8:10])[0]
        assert len(body)==n+10 and h(body[10:])[:16]==body[:8].hex()
        kept[worker].append(body[:8].hex())
    assert sum(wire.cost.values())<=budget
    if pair_fits: assert all(ids[k][best[k]].hex() in kept[k] for k in (0,1))
    return dict(ids=kept,bytes=dict(wire.cost),wire_hash=wire.digest.hexdigest(),used=sum(wire.cost.values()),best=[int(x) for x in best])


if __name__=='__main__':
    lock=json.loads((ROOT/'pointer-input-lock.json').read_text())
    count=0
    out=ROOT/'pointer-forecasts.jsonl.gz'
    link=Link()
    try:
        with out.open('wb') as f,gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0) as z:
            for source,budgets in BUDGETS.items():
                p=CACHE/f'{source}-workers.json'
                d=CACHE/f'{source}-refs.sqlite'
                assert h(p.read_bytes())==lock[source]['worker_packets'] and h(d.read_bytes())==lock[source]['db_sha']
                records=json.loads(p.read_text())
                db=sqlite3.connect(d.resolve().as_uri()+'?mode=ro',uri=True)
                for r in records:
                    for policy in METHODS:
                        for b in budgets:
                            for limit in ('one','fill'):
                                pred=run(r['case'],r['workers'],db,link,policy,b,limit=='one')
                                pred.update(source=source,case=r['case'],policy=policy,budget=b,limit=limit)
                                z.write((json.dumps(pred,sort_keys=True,separators=(',',':'))+'\n').encode())
                                count+=1
                db.close()
    finally:
        link.close()
    (ROOT/'pointer-forecast-lock.json').write_text(json.dumps(dict(forecasts=h(out.read_bytes()),count=count,selector=h(Path(__file__).read_bytes()),protocol=h((ROOT/'pointer-protocol.json').read_bytes())),sort_keys=True)+'\n',encoding='utf8')


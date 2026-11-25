"""Exact or approximate top-one BM25 selection using write-time metadata and logged source reads."""
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
import re
import zlib

WORDS=re.compile(r"[^\W_]+",re.UNICODE)
def bag(text):
    return Counter(WORDS.findall(text.casefold()))
@lru_cache(maxsize=100000)
def mask(word):
    digest=hashlib.blake2b(word.encode(),digest_size=16,person=b"agent-qview-v1").digest()
    a=int.from_bytes(digest[:8],"little");b=int.from_bytes(digest[8:],"little")|1
    return sum(1<<((a+i*b)%256) for i in range(4))

def write_view(windows,first_question):
    interest=set(bag(first_question))
    doc_frequency=Counter();info=[];complete=[]
    for w in windows:
        counts=bag(w["text"]);complete.append(counts);doc_frequency.update(counts.keys())
        known={s:n for s,n in counts.items() if s in interest}
        unknown_max=max((n for s,n in counts.items() if s not in interest),default=0)
        signature=0
        for s in counts: signature |= mask(s)
        info.append({"coords":[w["e"],w["l"],w["h"],w["edge"],int(w["eligible"])],
                     "length":sum(counts.values()),"known":known,"unknown_max":unknown_max,
                     "max":max(counts.values(),default=0),"bits":signature})
    return {"first":sorted(interest),"df":dict(doc_frequency),"rows":info}, complete

def size_of(data):
    return len(zlib.compress(json.dumps(data,separators=(",",":"),ensure_ascii=False,sort_keys=True).encode(),level=6))

def sizes(view,complete):
    # Each representation is a stand-alone compressed payload for the same collection.
    coords=[r["coords"] for r in view["rows"]]
    lengths=[r["length"] for r in view["rows"]]
    known=[r["known"] for r in view["rows"]];bounds=[r["unknown_max"] for r in view["rows"]]
    masks=[r["bits"].to_bytes(32,"little").hex() for r in view["rows"]]
    common=[coords,lengths,view["df"]]
    projected=[*common,view["first"],known,bounds]
    inverted={}
    for i,doc in enumerate(complete):
        for w,f in doc.items():inverted.setdefault(w,[]).append([i,f])
    return dict(scan=size_of(coords),df_scan=size_of(common),projected=size_of(projected),exact_lazy=size_of(projected),
                bloom_scan=size_of([*projected,masks]),bloom_lazy=size_of([*projected,masks]),
                bloom_cold=size_of([*common,[r["max"] for r in view["rows"]],masks]),
                inverted=size_of([coords,lengths,inverted]))

def select(view,question,method,fetch,postings=None):
    rows=view["rows"];terms=sorted(bag(question))
    eligible=[i for i,r in enumerate(rows) if r["coords"][4]]
    if not eligible:return None
    if method=="scan":
        docs=[fetch(i) for i in range(len(rows))]
        df=Counter()
        for doc in docs:df.update(doc.keys())
        lengths=[sum(d.values()) for d in docs]
        assert lengths==[r["length"] for r in rows]
    else:
        docs=None;df=({w:len(postings.get(w,{})) for w in terms} if method=="inverted" else view["df"]);lengths=[x["length"] for x in rows]
    n=len(rows);avg=sum(lengths)/n or 1
    weights={w:math.log1p((n-df[w]+.5)/(df[w]+.5)) for w in terms if df.get(w,0)>0}
    active=tuple(weights)
    def score(counts,i):
        norm=1.2*(.25+.75*lengths[i]/avg)
        return sum(weights[w]*counts[w]*2.2/(counts[w]+norm) for w in active if counts.get(w,0)>0)
    if method in ("scan","df_scan","inverted"):
        if method=="inverted":
            allowed=set(eligible);hits={}
            for w in active:
                for i,count in postings.get(w,{}).items():
                    if i in allowed:
                        norm=1.2*(.25+.75*lengths[i]/avg)
                        hits[i]=hits.get(i,0.)+weights[w]*count*2.2/(count+norm)
            return max(hits,key=lambda i:(hits[i],-i)) if hits else eligible[0]
        return max(eligible,key=lambda i:score(docs[i] if docs is not None else fetch(i),i))
    captured=set() if method=="bloom_cold" else set(view["first"])
    unknown=[w for w in active if w not in captured]
    sigs={w:mask(w) for w in unknown}
    exact={}
    upper={}
    def can_occur(w,r):
        if method in ("bloom_lazy","bloom_scan","bloom_cold"):
            return (r["bits"]&sigs[w])==sigs[w]
        return True
    for i in eligible:
        r=rows[i]
        low={} if method=="bloom_cold" else r["known"]
        limit=r["max"] if method=="bloom_cold" else r["unknown_max"]
        possible=[w for w in unknown if limit>0 and can_occur(w,r)]
        if method=="projected" or not possible:
            exact[i]=score(low,i)
        elif method=="bloom_scan":
            exact[i]=score(fetch(i),i)
        else:
            bound=dict(low);bound.update({w:limit for w in possible})
            upper[i]=score(bound,i)
    best=max(exact,key=lambda i:(exact[i],-i)) if exact else None
    best_score=exact[best] if best is not None else -1.0
    for i in sorted(upper,key=lambda j:(-upper[j],j)):
        if upper[i]<best_score or (upper[i]==best_score and best is not None and i>=best):
            break
        observed=score(fetch(i),i)
        assert observed<=upper[i]+1e-12
        if observed>best_score or (observed==best_score and (best is None or i<best)):
            best=i;best_score=observed
    return best


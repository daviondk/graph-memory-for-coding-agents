"""Bounded mutable checkpoint; immutable task and shared codec/model are the only external inputs."""
import heapq,math,zlib
import numpy as np
from shared import D,read,prior
from risk import features

DICTIONARY=(D/"python_prior.bin").read_bytes()
RISK=read(D/"risk_model.json")
BETA=np.array(RISK["beta"])
GEOMETRY=RISK["geometry"]
WIDTH=np.zeros(3)
for off,length,count in GEOMETRY:
    needed=1+(off+length-1)//12
    if needed<=3:WIDTH[needed-1]+=count
WIDTH=WIDTH/WIDTH.sum()

# (state/ranking, use a corpus-wide fixed dictionary, readmission of boundary fragment)
METHODS={
    "lru":("lru",False,None),"point":("point",False,None),"typed":("typed",False,None),"mixed":("mixed",False,None),
    "dict_lru":("lru",True,None),"dict_mixed":("mixed",True,None),
    "dict_center":("mixed",True,"center"),"dict_neighbor":("mixed",True,"neighbor"),
    "cal_pages":("cal",True,None),"cal_center":("cal",True,"center"),"cal_neighbor":("cal",True,"neighbor"),
    "plain_neighbor":("mixed",False,"neighbor")}
CANDIDATES=["dict_neighbor","cal_pages","cal_neighbor","plain_neighbor"]
CONTROLS=["lru","point","typed","mixed","dict_lru","dict_mixed","dict_center","cal_center"]

def pack(state,dictionary):
    if not dictionary:return prior.pack(state)
    comp=zlib.compressobj(level=3,zdict=DICTIONARY)
    return b"SW3"+comp.compress(prior.jsonbytes(state))+comp.flush()

def unpack(blob,dictionary):
    if not dictionary:return prior.payload(blob)
    assert blob[:3]==b"SW3"
    dec=zlib.decompressobj(zdict=DICTIONARY)
    import json
    state=json.loads(dec.decompress(blob[3:])+dec.flush())
    assert dec.eof and not dec.unused_data and not dec.unconsumed_tail
    return state

def initial(method):
    rule,codec,fill=METHODS[method]
    return pack(["mixed" if rule=="cal" else rule,0,[],[],[]],codec)

def calibrated_order(pages, meta, last, issue):
    z=features(pages,meta,last,issue)@BETA; probability=np.exp(z-z.max())
    # Dissolved intervals never count toward an intact edit; update marginal values on each eviction.
    links={(p,a):j for j,(p,a,b,age,code) in enumerate(pages)}
    n=len(pages);chains=[];members=[[] for _ in pages];values=np.zeros(n)
    for j in range(n):
        span=[j]
        for k,mass in enumerate(WIDTH):
            if k:
                p,a,b,age,code=pages[span[-1]]
                nxt=links.get((p,b+1))
                if nxt is None:break
                span.append(nxt)
            weight=float(mass*probability[j]);i=len(chains);chains.append((tuple(span),weight))
            for m in span:members[m].append(i);values[m]+=weight
    rank={v:k for k,v in enumerate(prior.order(pages,meta))}
    prices=[len((f"@@ {p} {a}..{b} @@\n{c}\n").encode("utf8")) for p,a,b,age,c in pages]
    stamps=[0]*n;live=[True]*len(chains)
    heap=[(values[j]/prices[j],-rank[j],j,0) for j in range(n)]
    heapq.heapify(heap);used=set();ordered=[]
    while heap:
        _,_,j,stamp=heapq.heappop(heap)
        if j in used or stamp!=stamps[j]:continue
        used.add(j);ordered.append(j)
        for cid in members[j]:
            if not live[cid]:continue
            live[cid]=False
            for m in chains[cid][0]:
                if m in used:continue
                values[m]-=chains[cid][1];stamps[m]+=1
                heapq.heappush(heap,(values[m]/prices[m],-rank[m],m,stamps[m]))
    return ordered

def trim(row,n,side,ss):
    path,lo,hi,_,_=row
    if side=="left":end=lo+n-1;start=lo
    else:end=hi;start=hi-n+1
    items=[ss[path][i] for i in range(start,end+1)]
    return (path,start,end,max(t for s,t in items),"\n".join(s for s,t in items))

def transition(method,blob,event,static,weights,budget=4096):
    if method in ("lru","point","typed","mixed"):
        return prior.transition(blob,event,static,weights,budget)
    rule,codec,fill=METHODS[method]
    storage="mixed" if rule=="cal" else rule
    original=unpack(blob,codec);t,states,meta,hist,last=prior.materialize(original)
    assert original[0]==storage
    t+=1; name,args,output=event
    if storage!="lru":prior.write_event(hist,event,states["rebase"],t)
    if storage in ("typed","mixed"):
        path=prior.rel(args.get("path"))
        if prior.success(args.get("command"),path,output):
            last[:]=[(path,len(str(args.get("old_str","")).splitlines()),t)]
    prior.advance(states,meta,event,t)
    ss=states["rebase"];pages=prior.pages(ss)
    def dump(discarded,rows=pages):
        return pack(prior.snapshot(storage,t,ss,meta,hist,last,rows,discarded),codec)
    output=dump(set());pre=len(output);attempts=1;dropped=0
    if pre>budget:
        ordered=calibrated_order(pages,meta,last,static["issue"]) if rule=="cal" and pages else prior.eviction_order(rule,pages,meta,hist,last,t,static,weights) if pages else []
        lo=0;hi=min(1,len(pages));output=dump(set(ordered[:hi]));attempts+=1
        while len(output)>budget and hi<len(pages):
            lo,hi=hi,min(len(pages),2*hi);output=dump(set(ordered[:hi]));attempts+=1
        while len(output)<=budget and lo+1<hi:
            mid=(lo+hi)//2;new=dump(set(ordered[:mid]));attempts+=1
            if len(new)<=budget:hi=mid;output=new
            else:lo=mid
        dropped=hi
        if len(output)>budget:
            output=pack([storage,t,[],[],[]],codec);attempts+=1
        elif hi>0 and fill:
            j=ordered[hi-1];row=pages[j];path,a,b,age,_=row
            gone=set(ordered[:hi-1]);remain={k for k in range(len(pages)) if k not in gone and k!=j}
            left=any(pages[k][0]==path and pages[k][2]==a-1 for k in remain)
            right=any(pages[k][0]==path and pages[k][1]==b+1 for k in remain)
            best=None
            for direction in ("left","right"):
                lower=0;upper=b-a+1;cached=None
                while lower+1<upper:
                    n=(lower+upper)//2
                    rr=pages.copy();rr[j]=trim(row,n,direction,ss);trial=dump(gone,rr);attempts+=1
                    if len(trial)<=budget:lower=n;cached=trial
                    else:upper=n
                if not lower:continue
                mid=a+(lower-1)/2 if direction=="left" else b-(lower-1)/2
                close=-abs(mid-meta["center"][path])
                connected=int(left if direction=="left" else right)
                score=(lower,close) if fill=="center" else (lower*(1+connected),lower,close)
                if best is None or score>best[0]: best=(score,cached)
            if best:output=best[1]
    assert len(output)<=budget
    prior.wordset.cache_clear()
    return output,(pre,len(output),dropped,attempts)


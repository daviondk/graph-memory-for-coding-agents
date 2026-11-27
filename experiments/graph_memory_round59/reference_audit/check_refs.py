"""Independent source reconstruction, observed SQLite counters, and codec round trips."""
from collections import Counter, defaultdict, deque
from contextlib import closing
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import struct
import sys
from tempfile import TemporaryDirectory
import zlib

HERE=Path(__file__).resolve().parent
REF=HERE.parent/"references"
sys.path.insert(0,str(REF))
from measure_refs import inputs  # Published stream inventory only. No scorer or charging function.
from packet import encode,decode
from ref_reader import ReferenceReader
from block_store import BlockStore
from checkpoint import persist

SHA="0123456789abcdef0123456789abcdef01234567"
FMT=struct.Struct("<4sI20sII")


def uleb(xs):
    raw=bytearray()
    for x in xs:
        assert x>=0
        while x>=128:
            raw.append(128+x%128)
            x//=128
        raw.append(x)
    return bytes(raw)


def ranks(history, anchor, freqs, npaths):
    scores=Counter(x for event in history if anchor in event for x in event)
    order=sorted((x for x in range(npaths) if x!=anchor),key=lambda x:(-scores[x],-freqs[x],x))[:8]
    return [(x,scores[x]) for x in order]


def selections(prefix):
    recent=defaultdict(list)
    for i,body in enumerate(prefix):
        for x in body:
            recent[x].append(i)
    full=set(i for ids in recent.values() for i in ids[-8:])
    recent_freq=Counter(x for body in prefix[-128:] for x in body)
    weight={}
    charges={}
    for j in full:
        body=prefix[j]
        n=len(uleb(body))
        charges[j]=n+len(uleb((j,n)))
        weight[j]=Fraction(n*sum(1+recent_freq[x] for x in body),charges[j])
    keep=set()
    remaining=1024-40
    for j in sorted(full,key=lambda j:(weight[j],j),reverse=True):
        cost=charges[j]
        if cost<=remaining:
            keep.add(j)
            remaining-=cost
    return dict(full=full,demand1024=keep)


def prepare(stream,panel):
    fence=sum(2<=len(names)<=64 for _,names in stream)//2
    paths={}
    data=[]
    recent=deque(maxlen=32)
    post=[]
    orders=hashlib.sha256()
    for step,(rev,names) in enumerate(stream):
        names=names if len(names)<=64 else []
        if len(data)>=fence and len(names)>=2:
            sha=int(rev,16)
            if panel=="B" and step>=64:
                name=names[sha%len(names)]
            elif panel=="long" and step>=len(stream)//2 and sha%11==0:
                name=names[(sha//11)%len(names)]
            else:
                name=None
            if name is not None:
                f=paths.get(name,-1)
                counts=Counter(x for entry in recent for x in entry)
                expected=ranks(data,f,counts,len(paths))
                orders.update(json.dumps(expected,separators=(",",":")).encode()+b"\n")
                post.append(f)
        ids=tuple(paths.setdefault(p,len(paths)) for p in names)
        recent.append(ids)
        if len(ids)>=2:
            data.append(ids)
            if len(data)==fence:
                saved_revision=rev
    return data[:fence],saved_revision,post,orders.hexdigest()


def reference_layouts(ids,fence):
    ids=list(sorted(ids))
    def gaps(seq):
        last=-1
        ds=[]
        for j in seq:
            ds.append(j-last-1)
            last=j
        return uleb(ds)
    chosen=set(ids)
    holes=[j for j in range(fence) if j not in chosen]
    bitmap=bytearray((fence+7)//8)
    for j in ids:
        bitmap[j>>3] |= 1<<(j%8)
    return [uleb(ids),gaps(ids),gaps(holes),bytes(bitmap)]


def copy_payload(members):
    out=b""
    for j,body in sorted(members.items()):
        b=uleb(body)
        out+=uleb((j,len(b)))+b
    return out


def frame(code,items,fence,count):
    raw=FMT.pack(b"R59"+bytes((code,)),fence,bytes.fromhex(SHA),count,len(items))+items
    return raw+struct.pack("<I",zlib.crc32(raw))


def audit_source(raw):
    results={}
    for origin,panel,repo,stream in inputs():
        key="/".join((origin,panel,repo))
        states=raw["cases"][key]
        history,rev,queries,ranksha=prepare(stream,panel)
        assert all(x["ranking_sha"]==ranksha for x in states.values())
        selections_by_name=selections(history)
        outcomes={}
        for selection,keep in sorted(selections_by_name.items()):
            members={j:history[j] for j in keep}
            rawcopy=copy_payload(members)
            formats=reference_layouts(keep,len(history))
            packed=min(len(p) for vals in (formats,[zlib.compress(p,1) for p in formats]) for p in vals)
            sizes={"lazy":40+packed,"eager":40+packed,"compressed":40+min(len(rawcopy),len(zlib.compress(rawcopy,1))),
                   "copy":40+len(rawcopy)}
            total_body=sum(len(uleb(body)) for body in members.values())
            touched=set()
            touch=[]
            for f in queries:
                first={j for j in keep-touched if f in members[j]}
                touched.update(first)
                touch.append(sum(len(uleb(members[j])) for j in first))
            arms={k:states[selection+"/"+k] for k in sizes}
            for k,row in arms.items():
                s=row["setup"]
                assert s["write"]==s["load"]==sizes[k] and s["receipt"]==20
                assert s["selected_bodies"]==total_body and s["selected"]==len(keep)
                assert s["source"]==(total_body if k=="eager" else 0)
                assert [q[0] for q in row["queries"]]==queries
            assert [q[5] for q in arms["lazy"]["queries"]]==touch
            totals=[0]
            strict_raw=0
            for i in range(len(queries)+1):
                if i:
                    totals.append(totals[-1]+touch[i-1])
                for k in ("copy","compressed","eager"):
                    base=arms[k]["queries"]
                    lazy=arms["lazy"]["queries"]
                    if i:
                        a,b=base[i-1],lazy[i-1]
                        assert a[2]==b[2] and b[4]-a[4]==touch[i-1]
                    delta=(2*(sizes[k]-sizes["lazy"])+arms[k]["setup"]["source"]-totals[i])
                    if k=="copy":
                        assert delta>=total_body+2*len(keep)
                        strict_raw+=delta>0
            n=len(queries)
            horizons={}
            for h in sorted(set(min(n,x) for x in (0,1,4,16,n))):
                def observed_cost(which):
                    x=arms[which]
                    s=x["setup"]
                    return s["write"]+s["load"]+s["receipt"]+s["source"]+sum(a[2]+a[4] for a in x["queries"][:h])
                baseline=observed_cost("lazy")
                delta={k:observed_cost(k)-baseline for k in ("copy","compressed","eager")}
                for k,v in delta.items():
                    assert v==2*(sizes[k]-sizes["lazy"])+arms[k]["setup"]["source"]-totals[h]
                horizons[str(h)]=delta
            outcomes[selection]=dict(selected=len(keep),bodies=total_body,touched_bytes=totals[-1],
                 selected_touched=len(touched),sizes=sizes,delta_at_horizon=horizons,positive_raw_prefixes=strict_raw)
        results[key]=dict(queries=len(queries),ranking_sha=ranksha,arms=len(states),selection=outcomes)
    assert len(results)==len(raw["cases"])==33
    return results


def packets():
    rng=random.Random(59209)
    counts=Counter()
    for n in (0,1,2,7,8,9,31,127,128,129,255,256,399,400,401,1025):
        samples=[set(),set(range(n)),set(range(0,n,3)),set(range(max(0,n-3),n))]
        samples.extend({j for j in range(n) if rng.random()<p} for p in (.02,.15,.50,.90,.99))
        for s in samples:
            m={j:(2,127+j,16384+j) for j in s}
            payloads=[copy_payload(m),*reference_layouts(s,n)]
            for k,p in enumerate(payloads):
                for code,data in ((k,p),(k+8,zlib.compress(p,1))):
                    packet=frame(code,data,n,len(s))
                    ids,b=decode(packet,n,bytes.fromhex(SHA))
                    assert ids==s and b==(m if k==0 else {})
                    counts["forced_frames"]+=1
            for mode in ("copy","compressed","eager","lazy"):
                data=encode(m,n,SHA,mode)
                ids,b=decode(data,n,bytes.fromhex(SHA))
                assert ids==s and b==(m if mode in ("copy","compressed") else {})
                counts["production_frames"]+=1
    return dict(counts)


def sql_guards():
    counts=Counter()
    with TemporaryDirectory(dir=HERE) as folder:
        dbpath=Path(folder)/"test.sqlite"
        n=404
        history=[(0,1+j,1000+j) for j in range(n)]
        revisions=[hashlib.sha1(("commit"+str(j)).encode()).hexdigest() for j in range(n+1)]
        with closing(BlockStore(dbpath,"filelist",True)) as writer:
            for j,ids in enumerate(history):
                writer.append(j,revisions[j],ids)
        allpaths=1+max(v for ids in history for v in ids)
        for group in ([],[0,7,127,128,n-1],list(range(n))):
            members={j:history[j] for j in group}
            for arm in ("copy","compressed","eager","lazy"):
                encoded=encode(members,n,revisions[n-1],arm)
                for issue in ("valid","wrong_crc","other_revision","other_count"):
                    framebytes=encoded
                    if issue=="wrong_crc":
                        framebytes=encoded[:-1]+bytes([encoded[-1]^1])
                    elif issue=="other_revision":
                        framebytes=encode(members,n,revisions[0],arm)
                    elif issue=="other_count":
                        framebytes=encode(members,n+1,revisions[n-1],arm)
                    with closing(sqlite3.connect(dbpath)) as db:
                        persist(db,framebytes)
                    with closing(ReferenceReader(dbpath,arm)) as r:
                        assert r.rejected==(issue!="valid")
                        assert r.selected==(set(group) if issue=="valid" else set())
                        for anchor in (0,128,0,1500):
                            expected=ranks(history,anchor,Counter(),allpaths)
                            rank,_=r.read(anchor,Counter(),list(range(9)))
                            assert rank==expected
                            counts["sqlite_ranks"]+=1
                    counts["sqlite_reopens"]+=1
        # Latest frame becomes obsolete after a genuine committed append and close.
        with closing(BlockStore(dbpath,"filelist")) as writer:
            persist(writer.db,encode({0:history[0]},n,revisions[n-1],"lazy"))
            writer.append(n,revisions[n],(0,900))
        with closing(ReferenceReader(dbpath,"lazy")) as r:
            assert r.rejected
            expected=ranks(history+[(0,900)],900,Counter(),allpaths)
            assert r.read(900,Counter(),list(range(9)))[0]==expected
        # Numerically concrete counterexample with common members plus private ownership.
        hist={j:tuple(range(32))+(32+j,) for j in range(128)}
        rankcount=Counter(x for body in hist.values() for x in body)
        counterpath=Path(folder)/"counter.sqlite"
        with closing(BlockStore(counterpath,"filelist",True)) as w:
            for j,ids in hist.items():
                w.append(j,revisions[j],ids)
        charges={}
        sizes={}
        for arm in ("copy","compressed","eager","lazy"):
            encoded=encode(hist,len(hist),revisions[len(hist)-1],arm)
            with closing(sqlite3.connect(counterpath)) as db:
                persist(db,encoded)
            with closing(ReferenceReader(counterpath,arm)) as r:
                answer,work=r.read(0,rankcount,sorted(rankcount,key=lambda x:(-rankcount[x],x))[:9])
                assert answer==ranks(hist.values(),0,rankcount,len(rankcount))
                sizes[arm]=len(encoded)
                charges[arm]=len(encoded)+r.loaded_bytes+r.receipt_bytes+r.source_bytes+work[1]+work[3]
        assert charges["compressed"]<charges["lazy"]<charges["copy"]
        return dict(counts=counts,obsolete_after_append=True,counterexample=dict(sizes=sizes,charges=charges,
                    selected_bodies=sum(len(uleb(v)) for v in hist.values()),fence=len(hist)))


def main():
    z=REF/"runs.json.gz"
    raw=json.loads(gzip.decompress(z.read_bytes()))
    result=dict(source_sha=hashlib.sha256(z.read_bytes()).hexdigest(),panels=audit_source(raw),
                packets=packets(),sql=sql_guards())
    p=HERE/"results.json"
    if "--verify" in sys.argv:
        assert result==json.loads(p.read_bytes())
    else:
        p.write_text(json.dumps(result,sort_keys=True,indent=1)+"\n",encoding="utf-8")
    print(len(result["panels"]),sum(x["queries"] for x in result["panels"].values()),
          result["packets"],result["sql"])


if __name__=="__main__":
    main()

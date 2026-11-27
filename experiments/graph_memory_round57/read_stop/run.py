"""R57 replication + R56 long; use the original sealed query manifest for each panel."""
from collections import Counter,deque
from fractions import Fraction
import gzip
import json
from pathlib import Path
import sys

from stop import UNIT,MODES,decode,encode,prepare_meta,query
HERE=Path(__file__).resolve().parent
R=HERE.parent;R56=R.parent/"graph_memory_round56"
INPUTS={"replication":(R/"replication/events.json.gz",R/"replication/queries.json.gz"),
        "long":(R56/"event_intersection/long-events.json.gz",R56/"size_control/queries.json.gz")}

def load(f):
    return json.loads(gzip.decompress(f.read_bytes()) if f.suffix==".gz" else f.read_bytes())

def save(f,value,check):
    if check:assert load(f)==value;return
    buf=(json.dumps(value,separators=(",",":"),sort_keys=True)+"\n").encode()
    f.write_bytes(gzip.compress(buf,mtime=0) if f.suffix==".gz" else buf)

def replay(stream,prior):
    by={r["t"]:r for r in prior}
    ids={};freq=Counter();window=deque()
    payloads={};all_episodes={};tags={m:{} for m in MODES};out=[];writes=Counter()
    for t,(sha,raw) in enumerate(stream):
        paths=raw if len(raw)<=64 else []
        if t in by:
            row=by[t];assert row["sha"]==sha
            anchor=row["anchor"]
            old=row["methods"]["fill6_norm"]
            js=sorted(old["events"],key=lambda j:(len(all_episodes[j]),-j))
            assert len(js)==len(set(js))<=8 and all(0<=j<t and anchor in all_episodes[j] for j in js)
            gold=Counter()
            for j in js:
                e=all_episodes[j]
                for f in e:gold[f]+=Fraction(1,len(e)-1)
            expected=sorted((x for x in range(len(ids)) if x!=anchor),key=lambda x:(-gold[x],-freq[x],x))[:8]
            assert expected==old["rank"]
            heads=[(j,len(all_episodes[j])) for j in js]
            full=sum(len(payloads[j]) for j in js)
            info={}
            for mode in MODES:
                records={j:tags[mode][j] for j in js}
                calls=[]
                def read(j):
                    assert j in js and j not in calls
                    calls.append(j);return payloads[j]
                found=query(mode,heads,records,len(ids),anchor,freq,read)
                assert found["rank"]==expected and found["score_reads"]==calls
                assert [Fraction(n,UNIT) for n in found["scores"]]==[gold[x] for x in expected]
                info[mode]=dict(meta=sum(map(len,records.values())),ids_reads=found["ids_reads"],
                    ids_bytes=found["ids_bytes"],score_reads=found["score_reads"],score_bytes=found["score_bytes"])
            out.append(dict(t=t,sha=sha,anchor=anchor,events=js,full_bytes=full,rank=expected,
                       scores=[[gold[x].numerator,gold[x].denominator] for x in expected],methods=info))
        enc=[ids.setdefault(p,len(ids)) for p in paths]
        if len(window)==32:freq.subtract(window.popleft())
        freq.update(enc);window.append(enc)
        if len(enc)>=2:
            e=tuple(enc);raw=encode(e);assert decode(raw,len(e))==sorted(e)
            all_episodes[t]=e;payloads[t]=raw
            writes.update(dict(events=1,members=len(e),raw_bytes=len(raw)))
            for mode in MODES:
                tags[mode][t]=prepare_meta(mode,e,raw)
                writes[mode]+=len(tags[mode][t])
    return out,dict(writes)

def summary(rows):
    base=sum(r["full_bytes"] for r in rows);calls=sum(bool(r["events"]) for r in rows)
    out={"n":len(rows),"full_bytes":base,"full_requests":calls,
         "full_events":sum(len(r["events"]) for r in rows),"full_with_commands":base+calls}
    for mode in MODES:
        qs=[r["methods"][mode] for r in rows];meta=sum(i["meta"] for i in qs)
        s={"meta":meta}
        for target in ("ids","score"):
            reads=[len(q[target+"_reads"]) for q in qs]
            data=[q[target+"_bytes"] for q in qs]
            allbytes=[i["meta"]+b for i,b in zip(qs,data)]
            deltas=[u-r["full_bytes"] for u,r in zip(allbytes,rows)]
            s[target]=dict(requests=sum(reads),archive_bytes=sum(data),bytes=sum(allbytes),
                           with_commands=sum(allbytes)+sum(reads),
                           saved=sum(v<0 for v in deltas),tied=deltas.count(0),worse=sum(v>0 for v in deltas),
                           fewer_reads=sum(n<len(r["events"]) for n,r in zip(reads,rows)),
                           no_reads=sum(not n and bool(r["events"]) for n,r in zip(reads,rows)))
        out[mode]=s
    return out

def main():
    verify="--verify" in sys.argv
    raw={};results={}
    for panel,(p,h) in INPUTS.items():
        streams=load(p);ref=load(h)
        if panel=="long":ref=ref["long"]
        groups={};storage=Counter()
        for repo,stream in streams.items():
            groups[repo],writes=replay(stream,ref[repo])
            storage.update(writes)
        rows=[r for rs in groups.values() for r in rs]
        raw[panel]=groups
        results[panel]=dict(pooled=summary(rows),projects={k:summary(v) for k,v in groups.items()},build=dict(storage))
        print(panel,"full",results[panel]["pooled"]["full_bytes"],
              [(m,results[panel]["pooled"][m]["ids"]["bytes"],results[panel]["pooled"][m]["score"]["bytes"]) for m in MODES],flush=True)
    save(HERE/"queries.json.gz",raw,verify);save(HERE/"results.json",results,verify)
if __name__=="__main__":main()

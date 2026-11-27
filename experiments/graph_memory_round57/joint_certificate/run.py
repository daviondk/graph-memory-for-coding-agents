"""Decode the projected input, then compare certificate outputs with independent exact scores."""
from collections import Counter,deque
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

from certificate import certify,materialize

HERE=Path(__file__).resolve().parent
R=HERE.parent
PAIR=R/"seed_pair"
INPUTS={"new":PAIR/"events.json.gz","replication":R/"replication/events.json.gz",
        "long":R.parents[0]/"graph_memory_round56/event_intersection/long-events.json.gz"}

def load(p):
    d=p.read_bytes()
    return json.loads(gzip.decompress(d) if p.suffix==".gz" else d)

def write(p,d,verify):
    if verify:assert load(p)==d,p;return
    raw=(json.dumps(d,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)

def oracle(selected,archive,a,b,pool,freq):
    pair=Counter();joint=Counter()
    for j in selected:
        event=archive[j]
        seeds=int(a in event)+int(b in event)
        assert seeds in (1,2)
        for x in event:
            if x==a or x==b:continue
            pair[x]+=Fraction(seeds,len(event)-1)
            if seeds==2:joint[x]+=Fraction(1,len(event)-2)
    norm=sum(pair.values())
    scores={x:(pair[x]/norm if norm else Fraction(0))+joint[x] for x in pool}
    ordered=sorted(pool,key=lambda x:(-scores[x],-pair[x],-freq[x],x))[:8]
    return [(x,scores[x]) for x in ordered]

def replay(stream,records):
    by={r["t"]:r for r in records}
    ids={};window=deque();freq=Counter();archive={};sha_id={};out=[]
    for t,(sha,raw) in enumerate(stream):
        paths=raw if len(raw)<=64 else []
        if t in by:
            row=by[t];assert sha==row["sha"]
            a,b=(ids.get(p,-1) for p in row["seeds"])
            selected=[sha_id[s] for s in row["evidence"]];assert len(set(selected))==len(selected)
            fallback=sorted(range(len(ids)),key=lambda f:(-freq[f],f))[:10]
            fallback=[x for x in fallback if x not in (a,b)]
            packet,cost=materialize(selected,archive,a,b)
            allowed=set(row["joint"])
            fetched=[]
            def fetch(j):
                assert j in selected and j not in fetched
                assert stream[j][0] in allowed and a in archive[j] and b in archive[j]
                fetched.append(j);return archive[j]
            answer,stats=certify(packet,freq,fallback,fetch)
            # This reference considers every earlier known path, not only the sparse rankable pool.
            gold=oracle(selected,archive,a,b,[x for x in range(len(ids)) if x not in (a,b)],freq)
            assert answer==gold and [x for x,s in answer]==row["ranks"]["joint"]
            assert cost["build_members"]==row["members"] and cost["joint_events"]==len(row["joint"])
            assert stats["reads"]==len(fetched)
            out.append(dict(sha=sha,t=t,rank=[x for x,s in answer],
                       scores=[[s.numerator,s.denominator] for x,s in answer],packet_sha256=sha256(packet).hexdigest(),
                       read_sha=[stream[j][0] for j in fetched],**cost,**stats))
        encoded=[ids.setdefault(path,len(ids)) for path in paths]
        freq.update(encoded)
        if len(window)==32:freq.subtract(window.popleft())
        window.append(encoded)
        if len(encoded)>=2:
            archive[t]=encoded;sha_id[sha]=t
    assert len(out)==len(records)
    return out

def summarize(rows):
    numeric=tuple(k for k,v in rows[0].items() if isinstance(v,(bool,int)) and k!="t")
    out={k:sum(r[k] for r in rows) for k in numeric}
    out.update(n=len(rows),has_joint=sum(r["joint_events"]>0 for r in rows),active_regions=sum(len(r["opened"]) for r in rows),
               packet_plus_members_bytes=out["packet_bytes"]+4*out["members"],full_bytes=4*out["build_members"],
               all_joint_bytes=4*out["joint_members"],queries_read=sum(r["reads"]>0 for r in rows),
               queries_packet_cheaper=sum(r["packet_bytes"]+4*r["members"]<4*r["build_members"] for r in rows))
    return out

def main():
    verify="--verify" in sys.argv
    groups={};summary={}
    for panel,path in INPUTS.items():
        source=load(path);ref=load(PAIR/(panel+"-queries.json.gz"))
        groups[panel]={repo:replay(stream,ref[repo]) for repo,stream in source.items()}
        rows=[row for rq in groups[panel].values() for row in rq]
        summary[panel]=dict(pooled=summarize(rows),projects={repo:summarize(rs) for repo,rs in groups[panel].items() if rs})
        print(panel,summary[panel]["pooled"],flush=True)
    write(HERE/"queries.json.gz",groups,verify);write(HERE/"results.json",summary,verify)
if __name__=="__main__":main()

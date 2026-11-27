"""Inspect a genuine historical cache miss against the bundled read-only SQLite database."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from functools import reduce
import json
from operator import xor
from pathlib import Path
import sqlite3

HERE=Path(__file__).resolve().parent


def unpack(raw):
    ids=[];v=0;shift=0
    for b in raw:
        v|=(b&127)<<shift
        if b<128:ids.append(v);v=0;shift=0
        else:shift+=7
    if shift:raise ValueError("incomplete varint")
    return ids


def inspect(hide=False):
    q=json.loads((HERE/"query.json").read_bytes())
    f=q["anchor"];paths=q["paths"];tie={int(k):v for k,v in q["tie"].items()}
    known={int(k):bytes.fromhex(v) for k,v in q["known"].items()}
    if hide:known.pop(min(known))
    packet=bytes.fromhex(q["summary_hex"])
    assert packet[0]==4
    n,x=unpack(packet[1:])
    deficit=n-len(known)
    def rank(bodies):
        counts=Counter(file for b in bodies for file in unpack(b) if file!=f)
        rows=[[i,counts[i]] for i in sorted(counts,key=lambda i:(-counts[i],-tie[i],i))[:8]]
        seen={i for i,_ in rows}
        for i in q["prior"]:
            if len(rows)>=8:break
            if i!=f and i not in seen:rows.append([i,0])
        return rows
    uri=(HERE/"source.sqlite").as_uri()+"?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri,uri=True)) as db:
        assert db.execute("SELECT MAX(j)+1 FROM event").fetchone()[0]==q["prefix"]
        def posting():
            return unpack(db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()[0])
        ledger=[];details=[]
        if deficit==1:
            missing=[x^reduce(xor,known,0)]
            method="one missing event recovered"
            assert missing[0] not in known
        else:
            ledger.append("posting(file)");missing=sorted(set(posting())-set(known))
            method="complete posting read"
        bodies=list(known.values())
        for j in missing:
            ledger.append("body("+str(j)+")")
            rev,b=db.execute("SELECT rev,members FROM event WHERE j=?",(j,)).fetchone()
            assert f in unpack(b);bodies.append(b)
            details.append(dict(id=j,commit=rev.hex(),members=[paths[str(i)] for i in unpack(b)]))
        rows=rank(bodies)
        audit=rank(db.execute("SELECT members FROM event WHERE j=?",(j,)).fetchone()[0] for j in posting())
        assert rows==q["expected"]==audit
    return dict(project=q["project"],post_restart_query=q["query"],prefix=q["prefix"],file=q["anchor_path"],count=n,
                known=len(known),deficit=deficit,summary_xor=x,selection=method,recovered=details,
                query_reads=ledger,full_index_verified=True,ranking=[[paths[str(i)],s] for i,s in rows])


if __name__=="__main__":
    p=ArgumentParser(description=__doc__);p.add_argument("--json",action="store_true")
    p.add_argument("--hide-one",action="store_true",help="withhold one additional cached body and exercise exact fallback")
    args=p.parse_args();r=inspect(args.hide_one)
    if args.json:print(json.dumps(r,sort_keys=True))
    else:
        print(f"{r['project']} | query {r['post_restart_query']} | {r['file']}")
        print(f"{r['known']} known of {r['count']} historical events. {r['selection']}.")
        print("SQLite query operations: "+", ".join(r["query_reads"]))
        for e in r["recovered"]:print(f"  event {e['id']} -> {e['commit']}")
        print("Top eight, checked independently against the complete SQLite posting list:")
        for name,score in r["ranking"]:print(f"{score:>3}  {name}")

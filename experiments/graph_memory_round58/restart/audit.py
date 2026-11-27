"""Reconstruct the retained sets and byte charges independently from source histories."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from checkpoint import Pinned,Reader,make_snapshot,persist
from bench_restart import ARMS,HERE,load,save,panels,prepare


def width(x):
    return max(1,(x.bit_length()+6)//7)


def chosen(events,cap,policy):
    if policy=="cold":return set(),0,0
    histories=defaultdict(list)
    for j,ids in enumerate(events):
        for f in ids:histories[f].append(j)
    eligible={j for entries in histories.values() for j in entries[-8:]}
    rate=Counter(f for ids in events[-128:] for f in ids)
    lengths={j:sum(map(width,events[j])) for j in eligible}
    charges={j:width(j)+width(lengths[j])+lengths[j] for j in eligible}
    if policy=="demand":
        def priority(j):
            return Fraction(lengths[j]*sum(1+rate[f] for f in events[j]),charges[j]),j
    elif policy=="largest":
        def priority(j):return lengths[j],j
    else:
        def priority(j):return j,j
    selected=set();used=40   # Independently count 4 magic + 4 horizon + 20 SHA + 4 count + 4 length + 4 CRC.
    for j in sorted(eligible,key=priority,reverse=True):
        if cap is None or used+charges[j]<=cap:
            selected.add(j);used+=charges[j]
    return selected,used,used if cap is None else cap


def real(p,repo,ops,logs):
    evs=[op[3] for op in ops if op[0]=="w"]
    weights=[sum(map(width,ids)) for ids in evs]
    split=len(evs)//2
    meta={k:chosen(evs[:split],cap,policy) for k,(policy,cap) in ARMS.items()}
    traces={k:[] for k in ARMS}
    for k in ARMS:
        rows=[r for r in logs if (r["panel"],r["project"],r["method"])==(p,repo,k)]
        assert len(rows)==3
        selected,use,written=meta[k]
        for row in rows:
            assert (row["stats"]["snapshot_events"],row["stats"]["snapshot_useful"],row["stats"]["snapshot_write"])==(len(selected),use,written)
            traces[k].append(row["queries"])
    all_inc=defaultdict(list);after_inc=defaultdict(list);known={k:set() for k in ARMS}
    tot=post=events=checks=0
    per={k:Counter() for k in ARMS}
    for op in ops:
        if op[0]=="w":
            _,j,rev,ids=op
            for f in ids:
                all_inc[f].append(j)
                if j>=split:after_inc[f].append(j)
            events+=1;continue
        _,f,tie,prior,expected=op
        incident=all_inc.get(f,[])
        counts=Counter(g for j in incident for g in evs[j])
        independently_sorted=sorted((g for g in tie if g!=f),key=lambda g:(-counts[g],-tie[g],g))[:8]
        assert [(g,counts[g]) for g in independently_sorted]==expected
        if events>=split:
            live={j for ids in after_inc.values() for j in ids[-8:]}
            early={j for j in incident if j<split}
            late=set(incident)-early
            hot=late&live
            for k,(selection,use,written) in meta.items():
                pinned=early&selection
                query=f not in known[k] or late!=hot
                if query and pinned==early:known[k].add(f)
                needed=(early-pinned)|(late-hot)
                expected_work=(int(query),(len(needed)+399)//400 if query else 0,
                               sum(map(width,incident)) if query else 0,len(needed),
                               sum(weights[j] for j in needed),len(pinned),len(hot))
                assert query or not needed
                for log in traces[k]:
                    dat=log[tot]
                    assert dat[0]==(1 if post<10 else 2) and tuple(dat[2:])==expected_work,(k,p,repo,f,dat,expected_work)
                    checks+=1
                per[k].update(postings=expected_work[2],bodies=expected_work[4])
            post+=1
        tot+=1
    report={}
    for k,observed in per.items():
        selection,use,written=meta[k]
        total=observed["postings"]+observed["bodies"]+2*written+(20 if k!="cold" else 0)
        report[k]=dict(charged_bytes=total,selected=len(selection),useful=use,written=written)
    return dict(all_q=tot,post_q=post,checked_post_query_records=checks,arms=report)


def synthetic():
    with TemporaryDirectory(dir=HERE,prefix="fault-") as td:
        path=Path(td)/"store.sqlite"
        writer=Reader(path,"shared",True)
        seq=[(0,1,3),(0,1),(0,2),(3,6)]*5
        rev=lambda j:hashlib.sha1(str(j).encode()).hexdigest()
        for i,ids in enumerate(seq):writer.append(i,rev(i),ids)
        blob,_,_=make_snapshot(writer.hot.live,len(seq),rev(len(seq)-1),"recent",130)
        persist(writer.db,blob);writer.close()
        h=Pinned(path,True);assert h.pinned and not h.rejected
        points=Counter(f for ids in seq for f in ids)
        prior=sorted(points,key=lambda f:(-points[f],f))[:9]
        def match(h,history):
            for f in [*points,-1]:
                c=Counter(g for ids in history if f in ids for g in ids)
                rank=sorted((g for g in points if g!=f),key=lambda g:(-c[g],-points[g],g))[:8]
                assert h.read(f,points,prior)[0]==[(g,c[g]) for g in rank]
        match(h,seq)
        broken=bytearray(blob);broken[44]^=1
        persist(h.db,broken);h.close();h=Pinned(path,True)
        assert h.rejected and not h.pinned;match(h,seq)
        persist(h.db,blob);h.append(len(seq),rev(len(seq)),(0,6));h.close()
        h=Pinned(path,True);assert h.rejected and not h.pinned;match(h,seq+[(0,6)])
        h.db.execute("DROP TABLE snapshot");h.close();h=Pinned(path,True)
        assert not h.pinned;match(h,seq+[(0,6)]);h.close()
        return dict(valid_snapshot=True,corruption_fallback=True,stale_fallback=True,missing_fallback=True,
                    checked_rankings=4*(len(points)+1))


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    logs=load(HERE/"runs.json.gz")["runs"]
    ds=panels();out={"projects":{},"fallback":synthetic()}
    for p in ("B","long"):
        for repo,rows in ds[p].items():
            ops,_=prepare(rows,p)
            out["projects"][p+"/"+repo]=real(p,repo,ops,logs)
    if args.verify:assert out==load(HERE/"audit.json")
    else:save(HERE/"audit.json",out)
    print("Verified",sum(v["checked_post_query_records"] for v in out["projects"].values()),"post-restart query records.")


if __name__=="__main__":
    main()

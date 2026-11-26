"""Registered supplemental comparison of partial vs whole lazy refills and the Yi variable-prefix baseline."""
from collections import Counter, deque
import argparse
from itertools import product
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np

import run
from partial import PartialStore, certify
from reserve_store import refresh, key, advance, ReserveStore
from core import M, OLD, connect, read
from bench import oracle
from stress import event

D=run.HERE


def finite():
    scores=list(product((-1,0,1),repeat=3))
    result={}
    for k,l in ((1,1),(1,2),(2,2),(2,3)):
        start=((-1,-1,-1),((),None))
        queue,seen,counts=deque([start]),{start},Counter()
        while queue:
            before,state=queue.popleft()
            for after in scores:
                dirty={i:(None if b<0 else b) for i,(a,b) in enumerate(zip(before,after)) if a!=b}
                full=sorted([(i,x) for i,x in enumerate(after) if x>=0],key=key,reverse=True)
                keep,bound,prefix=certify(state,dirty,l)
                assert list(prefix)==full[:len(prefix)]
                expected=advance(state,dirty,l,k)
                if bound is not None and len(prefix)<k:
                    assert expected is None
                    extra = [v for v in full if not prefix or key(v)<key(prefix[-1])][:l-len(prefix)]
                    nxt=refresh(prefix+tuple(extra),l)
                    assert nxt==refresh(full[:l],l)
                    counts["fallback"]+=1
                else:
                    nxt=(keep,bound)
                    assert expected==nxt
                run.check_state(nxt,full,k,l)
                counts["transitions"]+=1
                if (after,nxt) not in seen:
                    seen.add((after,nxt))
                    queue.append((after,nxt))
        result[f"k{k}-L{l}"]=dict(**counts,states=len(seen))
    return result


def probe_state(folder,work,l):
    a,b = connect(folder/(f"seq-{l}-a.sqlite")),connect(folder/(f"seq-{l}-b.sqlite"))
    ea,eb=PartialStore(a,l),ReserveStore(b,l,"lazy")
    n=0
    try:
        for q,rows in work.items():
            for r in rows:
                assert ea.update(q,r) and eb.update(q,r)
                assert ea.last[q]==eb.last[q]
                assert ea.event["cold_probes"]==eb.event["cold_probes"]
                assert ea.event["warm_probes"]==eb.event["warm_probes"]
                assert ea.event["warm_rows"]<=eb.event["warm_rows"]
                n+=1
        return n
    finally:
        a.close()
        b.close()


def stress(folder):
    db=connect(folder/"stress-partial.sqlite")
    try:
        s=PartialStore(db,12)
        ids=list(range(20))
        assert s.update("q",event(1,ids,[[i,i,20-i] for i in ids]))
        s.last.clear()
        assert s.update("q",event(2,[],[[i,i,-(20-i)] for i in range(8)]))
        assert s.get("q",2,8)==[(i,20-i) for i in range(8,16)]
        assert s._history("q",1,8)==[(i,20-i) for i in range(8)]
        return dict(s.event)
    finally:
        db.close()


def cost_difference(per,work,a,b,col):
    counts=np.array([len(rs) for rs in work.values()])
    differences=np.array([sum(per[a][f"{q}/{r['t']}"][col]-per[b][f"{q}/{r['t']}"][col] for r in rs) for q,rs in work.items()])
    boot=np.random.default_rng(541923).integers(len(work),size=(10000,len(work)))
    bounds=np.percentile(100*differences[boot].sum(1)/counts[boot].sum(1),[2.5,97.5]).tolist()
    return dict(saved=int(differences.sum()),saved_per100=100*differences.sum()/counts.sum(),ci95_per100=bounds,
                better=int((differences>0).sum()),worse=int((differences<0).sum()),tie=int((differences==0).sum()))


def main(args):
    reg={f:run.sha(D/f) for f in ["PARTIAL_PROTOCOL_RU.md","partial.py","partial_run.py","classic.py",
                                     "classic-registration.json","classic-results.json","registration.json","results.json"]}
    if args.register:
        assert not (D/"partial-results.json").exists()
        run.save("partial-registration.json",reg)
        return
    assert reg==read(D/"partial-registration.json")
    w=read(OLD/"workload.json.gz"); refs,_=oracle(w)
    costs={};out={};restart={};same={}
    with tempfile.TemporaryDirectory(dir=D) as scratch:
        folder=Path(scratch)
        with patch.object(run,"make",lambda db,name,l,create=True:PartialStore(db,l,"partial",create)):
            for l in (8,9,12,16):
                plan="partial-"+str(l)
                costs[plan],out[plan]=run.replay(folder/(plan+".sqlite"),"lazy",l,w,refs)
                restart[plan]=run.restart(folder/(plan+"-restart.sqlite"),"lazy",l,w,refs)
                same[str(l)]=probe_state(folder,w,l)
        extra=stress(folder)
    old=read(D/"results.json")["plans"]["lazy-12"]
    assert all(r["snapshot_hash"]==old["snapshot_hash"] for r in out.values())
    per=dict(read(D/"event-costs.json.gz")["plans"],**read(D/"classic-event-costs.json.gz")["plans"],**costs)
    comp={}
    for l in (8,9,12,16):
        for baseline in ("lazy","classic"):
            src=f"{baseline}-{l}"; target=f"partial-{l}"
            comp[f"{src} minus {target}"]={c:cost_difference(per,w,src,target,j) for j,c in enumerate(["warm_probes","warm_rows"])}
    result=dict(plans=out,restart=restart,identical_lazy_states=same,finite=finite(),stress=extra,comparison=comp)
    if args.verify:
        assert result==read(D/"partial-results.json")
        assert costs==read(D/"partial-event-costs.json.gz")["plans"]
        print("Verified all partial-refill states, SQL outputs, costs, and comparisons.")
    else:
        run.save("partial-results.json",result)
        run.save("partial-event-costs.json.gz",dict(columns=run.COLS,plans=costs))
        print([(p,s["warm_probes"],s["warm_rows"]) for p,s in out.items()])
        print(comp["classic-8 minus partial-8"],extra)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--register",action="store_true")
    parser.add_argument("--verify",action="store_true")
    main(parser.parse_args())


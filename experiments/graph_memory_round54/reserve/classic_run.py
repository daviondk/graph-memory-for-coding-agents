"""Apply the previously locked audit harness to the published variable-prefix comparator."""
from collections import Counter, deque
import argparse
from itertools import product
from pathlib import Path
import tempfile
from unittest.mock import patch

import run
from classic import ClassicStore, SUFFIX, prefix_step
from reserve_store import refresh, key
from core import M, OLD, connect, read
from bench import oracle
from stress import event

D=run.HERE


class CheckedClassic(ClassicStore):
    def update(self,q,row,fault=False):
        ok=super().update(q,row,fault)
        if ok:
            cache,bound=self.last[q][1]
            ref=self.db.execute("SELECT s.cid,s.score FROM source s WHERE s.q=? ORDER BY s.score DESC,s.cid",(q,)).fetchall()
            assert list(cache)==ref[:len(cache)]
            if bound is None:
                assert len(cache)==len(ref)
        return ok


def finite():
    all_scores=list(product((-1,0,1),repeat=3))
    answer={}
    for k,l in [(1,1),(1,2),(2,2),(2,3)]:
        empty=((-1,-1,-1),((),None))
        queue=deque([empty])
        seen={empty}
        counts=Counter()
        while queue:
            before,state=queue.popleft()
            for after in all_scores:
                delta={i:(None if b<0 else b) for i,(a,b) in enumerate(zip(before,after)) if a!=b}
                true=sorted([(i,s) for i,s in enumerate(after) if s>=0],key=key,reverse=True)
                prefix,complete=prefix_step(state,delta,l)
                assert list(prefix)==true[:len(prefix)]
                if complete:
                    assert list(prefix)==true
                if not complete and len(prefix)<k:
                    counts["fallback"]+=1
                    nxt=refresh(tuple(true[:l]),l)
                else:
                    nxt=prefix,None if complete else key(prefix[-1])
                assert list(nxt[0][:k])==true[:k]
                counts["transitions"]+=1
                if (after,nxt) not in seen:
                    seen.add((after,nxt))
                    queue.append((after,nxt))
        answer[f"k{k}-L{l}"]=dict(**counts,states=len(seen))
    return answer


def stress(path):
    db=connect(path)
    try:
        s=CheckedClassic(db,12)
        ids=list(range(20))
        s.update("q",event(1,ids,[[i,i,20-i] for i in ids]))
        s.last.clear()
        s.update("q",event(2,[],[[i,i,-(20-i)] for i in range(8)]))
        assert s.get("q",2,8)==[(i,20-i) for i in range(8,16)]
        e=s.event
        assert e["cold_rows"]==12 and e["warm_rows"]==8 and e["warm_probes"]==1
        plan=[x[-1] for x in db.execute("EXPLAIN QUERY PLAN "+SUFFIX,("q",12,12,8,8))]
        assert any("COVERING INDEX source_best" in r for r in plan)
        return dict(cost=dict(e),suffix_query_plan=plan)
    finally:
        db.close()


def main(args):
    reg={f:run.sha(D/f) for f in ["CLASSIC_PROTOCOL_RU.md","classic.py","classic_run.py","registration.json","results.json"]}
    if args.register:
        assert not (D/"classic-results.json").exists()
        run.save("classic-registration.json",reg)
        return
    assert reg==read(D/"classic-registration.json")
    work=read(OLD/"workload.json.gz")
    refs,_=oracle(work)
    out={}
    per={}
    restart={}
    with tempfile.TemporaryDirectory(dir=D) as scratch:
        folder=Path(scratch)
        with patch.object(run,"make",lambda db,name,l,create=True:CheckedClassic(db,l,"classic",create)):
            for l in [8,9,12,16]:
                plan="classic-"+str(l)
                per[plan],out[plan]=run.replay(folder/(plan+".sqlite"),"lazy",l,work,refs)
                restart[plan]=run.restart(folder/(plan+"-restart.sqlite"),"lazy",l,work,refs)
        extra=stress(folder/"stress.sqlite")
    earlier=read(D/"results.json")
    assert all(s["snapshot_hash"]==earlier["plans"]["lazy-12"]["snapshot_hash"] for s in out.values())
    original=read(D/"event-costs.json.gz")["plans"]
    pairs=dict(original,**per)
    contrast={str(l):run.contrast(pairs,work,"classic-"+str(l),"lazy-"+str(l)) for l in (8,9,12,16)}
    results=dict(plans=out,contrasts=contrast,stress=extra,finite=finite(),restart=restart)
    logged=dict(columns=run.COLS,plans=per)
    if args.verify:
        assert results==read(D/"classic-results.json")
        assert per==read(D/"classic-event-costs.json.gz")["plans"]
        print("Verified known algorithm and prefix scores.")
    else:
        run.save("classic-results.json",results)
        run.save("classic-event-costs.json.gz",logged)
        print([(p,x["warm_probes"],x["warm_rows"],x["mean_pairs"]) for p,x in out.items()])
        print(contrast)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--register",action="store_true")
    parser.add_argument("--verify",action="store_true")
    main(parser.parse_args())


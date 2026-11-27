"""Check subset algebra independently and inject replay/rollback/reopen at the DB boundary."""
from argparse import ArgumentParser
from collections import Counter
from functools import reduce
from hashlib import sha1
from itertools import combinations
from operator import xor
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from timing import HERE,BlockStore,Hot,SketchPolicy,save,load
from summary_cache import ABS,DELTA,BITS,NUM,XOR,MOMENTS,full,expand,encode,append,restore,unpack,varints,POST,EVENT


def powerset(xs):
    return (set(y) for k in range(len(xs)+1) for y in combinations(xs,k))


def fields(items,kind):
    values=[len(items)]
    if kind==XOR:values.append(reduce(xor,items,0))
    if kind==MOMENTS:values.extend((sum(items),sum(j**2 for j in items)))
    return tuple(values)


def nbytes(j):
    return max(1,(j.bit_length()+6)//7)


def algebra():
    examined=Counter()
    for universe in ((0,1,2,3,4,5,6),(0,126,127,128,129,16383,16384),
                     (1,31,128,(1<<30)-1,1<<30,(1<<40)+1)):
        for complete in powerset(universe):
            ids=tuple(sorted(complete))
            packet=full(ids)
            absolute=1+sum(map(nbytes,ids))
            delta=1+sum(nbytes(b-a-1) for a,b in zip((-1,*ids),ids))
            bitmap=1+nbytes(ids[0])+(ids[-1]-ids[0]+8)//8 if ids else absolute+1
            assert len(packet)==min(absolute,delta,bitmap) and expand(packet)==ids
            examined["full_shortest_roundtrips"]+=1
            limit=max(ids,default=0)+1
            for kind in (NUM,XOR,MOMENTS):
                forced=bytes([kind])+varints(fields(ids,kind))
                normal=encode(ids,kind)
                assert normal==(forced if len(forced)<len(packet) else packet)
                evolved=append(forced,limit)
                assert unpack(evolved[1:])==fields((*ids,limit),kind)
                assert expand(append(packet,limit))==(*ids,limit)
                for subset in powerset(ids):
                    found,deficit=restore(forced,subset,limit)
                    assert deficit==len(complete-subset)
                    expected={NUM:0,XOR:1,MOMENTS:2}[kind]
                    assert found==(ids if deficit<=expected else None)
                    examined["subset_trials"]+=1
            examined["different_full_sets"]+=1
    # This violation of inclusion yields a plausible wrong XOR result, not a detector.
    forced=bytes([XOR])+varints(fields({0,3},XOR))
    invalid=restore(forced,{1},4)[0]
    assert invalid==(1,2) and invalid!=(0,3)
    for kind in (NUM,XOR,MOMENTS):
        wrong,_=restore(bytes([kind])+varints(fields({0,3},kind)),{1,2},4)
        assert wrong==(1,2)
    return dict(counts=examined,invalid_subset_counterexample=dict(actual=[0,3],partial=[1],decoded=list(invalid)))


def integration():
    rng=random.Random(59372)
    stats=Counter()
    history=[]
    with TemporaryDirectory(dir=HERE,prefix="fault-") as temp:
        path=Path(temp)/"event.sqlite"
        db=BlockStore(path,"filelist",True)
        def rev(i):return sha1(str(i).encode()).hexdigest()
        def reload():
            nonlocal db
            db.close();db=BlockStore(path,"filelist")
            assert db.next_id==len(history)
            hot=Hot()
            policies={f"{cap}/{kind}":SketchPolicy(db,hot,kind,cap)
                      for cap in (64,256,4096) for kind in (None,NUM,XOR,MOMENTS)}
            assert all(not p.cache.items and not p.known for p in policies.values())
            stats["physical_reopens"]+=1
            return hot,policies
        def state():
            return dict(db.db.execute("SELECT f,js FROM posting")),list(db.db.execute("SELECT j,rev,members FROM event ORDER BY j"))
        def check_retained():
            for p in policies.values():
                assert p.cache.size<=p.cache.limit
                for (k,i),blob in p.cache.items.items():
                    if k==EVENT:
                        assert unpack(blob)==history[i]
                    elif k==POST:
                        src=tuple(j for j,v in enumerate(history) if i in v)
                        if blob[0]<NUM:assert expand(blob)==src
                        else:assert unpack(blob[1:])==fields(src,blob[0])
                    stats["resident_records_checked"]+=1
        def test_query(anchor):
            freq=Counter(i for row in history[-32:] for i in row)
            all_ids={i for row in history for i in row}
            tie={i:freq[i] for i in all_ids}
            prior=sorted(all_ids,key=lambda g:(-freq[g],g))[:9]
            cnt=Counter(g for row in history if anchor in row for g in row)
            rank=sorted((g for g in all_ids if g!=anchor),key=lambda g:(-cnt[g],-freq[g],g))[:8]
            for p in policies.values():
                answer,work=p.read(anchor,tie,prior)
                assert answer==[(g,cnt[g]) for g in rank]
                stats["rank_checks"]+=1
                for name in ("recovered0","recovered1","recovered2","failed","exact_hit"):
                    stats[name]+=work[name]
        def paths(j):
            family=[0,7,128,16384][j%4]
            return tuple(sorted({family,16+j%13,150+(j*7)%37,300+(j%9)}))
        for j in range(125):
            fs=paths(j);assert db.append(j,rev(j),fs);history.append(fs)
        hot,policies=reload()
        for j in range(125,221):
            for anchor in (0,16+j%13,7 if j%2 else 128,rng.choice((0,7,128,16384))):test_query(anchor)
            files=paths(j)
            if j in (127,128,160,193):
                before=state()
                try:db.append(j,rev(j),files,fault=True)
                except RuntimeError:pass
                else:raise AssertionError("fault did not roll back")
                assert before==state() and db.next_id==j
                test_query(files[0]);check_retained()
                stats["rolled_back"]+=1
            assert db.append(j,rev(j),files)
            history.append(files)
            if j==172:
                # Simulate process state loss after durable commit but before notification.
                hot,policies=reload()
            else:
                hot.append(j,files)
                for p in policies.values():p.after_write(j,files)
            if j in (127,128,160,193):
                before=state()
                assert not db.append(j,rev(j),files)
                try:db.append(j,rev(j+1000),files)
                except ValueError:pass
                else:raise AssertionError("conflicting replay accepted")
                assert before==state() and db.next_id==j+1
                stats["duplicate_suppressed"]+=1;stats["conflict_rejected"]+=1
            if j in (140,196):hot,policies=reload()
            if j%8==0:check_retained()
        for anchor in (-1,0,127,128,16384,7,128,0):test_query(anchor)
        check_retained()
        db.close()
    return stats


def directed_eviction():
    fixtures=[]
    with TemporaryDirectory(dir=HERE,prefix="subset-") as temp:
        path=Path(temp)/"store.sqlite"
        db=BlockStore(path,"filelist",True)
        rows=[]
        for j in range(261):
            row=(0 if j%11==0 else 1,1000+j)
            assert db.append(j,sha1(str(j).encode()).hexdigest(),row)
            rows.append(row)
        db.close();db=BlockStore(path,"filelist")
        incident=[i for i,r in enumerate(rows) if 0 in r]
        counts=Counter(g for j in incident for g in rows[j])
        freq=Counter(g for row in rows for g in row)
        prior=sorted(freq,key=lambda g:(-freq[g],g))[:9]
        expected=sorted((g for g in freq if g),key=lambda g:(-counts[g],-freq[g],g))[:8]
        expected=[(i,counts[i]) for i in expected]
        for kind in (NUM,XOR,MOMENTS):
            for missing in (0,1,2,3):
                h=SketchPolicy(db,Hot(),kind,4096)
                ans,_=h.read(0,freq,prior)
                assert ans==expected and h.cache.items[POST,0][0]==kind
                dropped=incident[-missing:] if missing else []
                for j in dropped:h.cache.drop((EVENT,j))
                rank,work=h.read(0,freq,prior)
                assert rank==expected
                success=missing<={NUM:0,XOR:1,MOMENTS:2}[kind]
                assert work["posting_calls"]==int(not success)
                assert work["body_calls"]==int(bool(missing))
                assert work["body_bytes"]==sum(len(varints(rows[j])) for j in dropped)
                assert work["recovered"+str(missing)]==int(success) and work["failed"]==int(not success)
                fixtures.append(dict(kind=kind,missing=missing,posting_calls=work["posting_calls"],
                                     body_calls=work["body_calls"],body_bytes=work["body_bytes"],recovered=success))
        db.close()
    return fixtures


if __name__=="__main__":
    parser=ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    out=dict(seed=59372,algebra=algebra(),integration=integration(),directed_eviction=directed_eviction())
    if verify:assert out==load(HERE/"audit.json")
    else:save(HERE/"audit.json",out)
    print(out)

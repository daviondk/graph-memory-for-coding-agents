"""Compare all retained receipts to independent prefix enumeration, including failure recovery."""
from collections import Counter
from hashlib import sha1
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from residual import BARE,COUNT,BlockStore,EVENT,POST,Residual,best,first,load,save,unpack,unpack_full
HERE=Path(__file__).resolve().parent
MODES=("native_count","native_bare","residual_only")
def rev(j):return sha1(str(j).encode()).hexdigest()

def reconstruction(h,f,data):
    if data[0]<COUNT:return set(unpack_full(data)),None
    n=None;off=1
    if data[0]==COUNT:
        n,sz=first(data[1:]);off+=sz
    ex=set(unpack(data[off:]))
    actual={j for j,fs in h.hot.live.items() if f in fs}
    actual.update(j for (kind,j),b in h.cache.items.items() if kind==EVENT and f in unpack(b))
    return actual|ex,n

def audit(temp):
    db=BlockStore(temp/"stress.sqlite","filelist",True)
    rng=Random(60228)
    history=[];stats=Counter()
    universe=(0,1,2,3,4,5,6,7,8,126,127,128,129,257,300)
    def files():return tuple(sorted(rng.sample(universe,rng.randint(2,7))))
    for j in range(40):
        fs=files();assert db.append(j,rev(j),fs);history.append(fs)
    policies=[Residual(db,b,m) for b in (47,149,1024) for m in MODES]
    def check():
        for h in policies:
            assert not h.cache.losses and not h.hot.live.losses
            for (kind,f),record in h.cache.items.items():
                if kind==EVENT: assert unpack(record)==history[f];continue
                exact={j for j,fs in enumerate(history) if f in fs}
                union,n=reconstruction(h,f,record)
                assert exact==union and (n is None or n==len(exact))
                stats["packets_checked"]+=1
    for j in range(40,161):
        fs=files()
        if j%29==0:
            try:db.append(j,rev(j),fs,fault=True)
            except RuntimeError:stats["rollback"]+=1
            else:raise AssertionError("rollback absent")
            assert db.next_id==j
        assert db.append(j,rev(j),fs);history.append(fs)
        for h in policies:
            if j%41: h.committed(j,fs)
            else: stats["skipped_commits_detected_on_read"]+=1
        if j%27==0:
            assert not db.append(j,rev(j),fs)
            stats["duplicate_rejected"]+=1
        for f in (rng.choice(universe),rng.choice(universe),-1):
            tied=Counter(k for row in history for k in row)
            priority=sorted(tied,key=lambda k:(-tied[k],k))[:9]
            count=Counter(k for row in history if f in row for k in row if k!=f)
            expected=best(count,f,tied,priority)
            for h in policies:
                assert h.read(f,tied,priority)[0]==expected
                stats["rank_checks"]+=1
            check()
        if j in (81,129):
            db.close();db=BlockStore(temp/"stress.sqlite","filelist")
            policies=[Residual(db,b,m) for b in (47,149,1024) for m in MODES]
            stats["physical_reopens"]+=1
    db.close()
    return stats

def failures(temp):
    db=BlockStore(temp/"fault.sqlite","filelist",True)
    for i in range(30):assert db.append(i,rev(i),(0,i+1))
    tie=Counter({i:1 for i in range(1,31)})
    prior=list(range(1,10))
    captured={}
    for mode in ("native_count","residual_only"):
        h=Residual(db,4096,mode)
        expected,_=h.read(0,tie,prior)
        assert h.cache.items[POST,0][0] in (COUNT,BARE)
        h.cache.drop((EVENT,0));h.cache.losses.clear()
        seen,n=reconstruction(h,0,h.cache.items[POST,0])
        assert 0 not in seen and len(seen)==29
        if mode=="native_count":
            rank,s=h.read(0,tie,prior)
            assert rank==expected and s["fallback"]==s["posting_calls"]==1
            captured["counted_silent_omission_detected"]=1
        else:
            rank,s=h.read(0,tie,prior)
            assert rank!=expected and s["posting_calls"]==0
            captured["bare_silent_omission_would_produce_wrong_rank"]=1
            h.invalidate()
            assert h.read(0,tie,prior)[0]==expected
            captured["explicit_invalidation_restores_exact_rank"]=1
    h=Residual(db,35,"residual_only")
    h.enroll=lambda *args:(_ for _ in ()).throw(RuntimeError("fault during delivery"))
    try:h.read(0,tie,prior)
    except RuntimeError:pass
    else:raise AssertionError("fault was not exercised")
    assert h.fence==db.next_id and not h.cache.items and not h.hot.live and not h.known
    del h.enroll
    assert h.read(0,tie,prior)[0]==expected
    captured["interrupted_read_fail_closed"]=1
    h=Residual(db,1024,"residual_only")
    for j in range(30,38):
        assert db.append(j,rev(j),(0,1));h.committed(j,(0,1))
    assert db.append(38,rev(38),(0,1))
    h.enroll=lambda *args:(_ for _ in ()).throw(RuntimeError("postcommit notification failure"))
    try:h.committed(38,(0,1))
    except RuntimeError:pass
    else:raise AssertionError("expected committed write fault")
    assert h.fence==db.next_id==39 and not h.hot.live and not h.cache.items
    del h.enroll
    assert h.read(0,tie,prior)[0][0]==(1,10)
    captured["interrupted_postcommit_fail_closed"]=1
    db.close()
    return captured
def main():
    import sys
    with TemporaryDirectory(dir=HERE) as t:
        result={"stress":audit(Path(t)),"fault":failures(Path(t))}
    if "--verify" in sys.argv:assert result==load(HERE/"audit.json")
    else:save(HERE/"audit.json",result)
    print(result)
if __name__=="__main__":main()


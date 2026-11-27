"""Certificate exhaustions and independent state checks after SQLite commits and evictions."""
from argparse import ArgumentParser
from collections import Counter,defaultdict
from hashlib import sha1
from itertools import combinations
import random
from tempfile import TemporaryDirectory
from pathlib import Path

from coverage import Coverage,Hot,EVENT,POST,EXCEPTION,parts,expand,unpack,pack_exceptions,possible_losses
from run_coverage import HERE,BlockStore,load,save


def subsets(seq):
    return (set(v) for k in range(len(seq)+1) for v in combinations(seq,k))


def algebra():
    checks=0;changes=0
    for truth in subsets([0,1,127,128,255,16384]):
        for resident in subsets(truth):
            for evidence in subsets(truth):
                n,terms=parts(pack_exceptions(len(truth),evidence))
                recon=resident.union(terms)
                assert (len(recon)==n)==(recon==truth)
                for removed in resident:
                    moved=(resident-{removed})|evidence|{removed}
                    assert moved==recon
                    changes+=1
                checks+=1
    return dict(subsets=checks,eviction_moves=changes)


class Observed(Coverage):
    """Only the test observer counts resulting event losses inside record maintenance."""
    def __init__(self,*args):
        super().__init__(*args);self.nested_drops=0

    def unavailable(self,j,files):
        before=len(self.cache.pending)
        super().unavailable(j,files)
        self.nested_drops+=len(self.cache.pending)-before


def direct():
    with TemporaryDirectory(dir=HERE,prefix="direct-") as folder:
        path=Path(folder)/"graph.sqlite"
        db=BlockStore(path,"filelist",True)
        history=[]
        for j in range(232):
            row=(0 if j%9==0 else 1,1000+j)
            assert db.append(j,sha1(str(j).encode()).hexdigest(),row);history.append(row)
        db.close();db=BlockStore(path,"filelist")
        incidence=[j for j,ids in enumerate(history) if 0 in ids]
        freq=Counter(f for ids in history for f in ids)
        prior=sorted(freq,key=lambda f:(-freq[f],f))[:9]
        records=[]
        for notify in (False,True):
            c=Observed(db,Hot(),4096,notify)
            expected,_=c.read(0,freq,prior,incidence)
            n,ex=parts(c.cache.items[POST,0])
            assert ex==() and n==len(incidence)
            for j in incidence[-5:]:c.cache.drop((EVENT,j))
            c.drain()
            n,ex=parts(c.cache.items[POST,0])
            assert set(ex)==(set(incidence[-5:]) if notify else set())
            recovered,work=c.read(0,freq,prior,incidence)
            assert recovered==expected and work["posting_calls"]==int(not notify)
            assert work["body_calls"]==1 and work["covered_missing_ids"]==(5 if notify else 0)
            records.append(dict(notify=notify,missing=5,sql_postings=work["posting_calls"],
                           sql_body_bytes=work["body_bytes"],sql_body_calls=work["body_calls"]))
        db.close()
    return records


def stress():
    rng=random.Random(60067);stats=Counter()
    history=[]
    with TemporaryDirectory(dir=HERE,prefix="stress-") as folder:
        db_path=Path(folder)/"graph.sqlite"
        db=BlockStore(db_path,"filelist",True)
        rev=lambda j:sha1(str(j).encode()).hexdigest()
        def event(j):
            group=rng.choice((2,2,2,3,4,6,9))
            return tuple(sorted(rng.sample([0,1,2,3,4,5,6,7,8,9,126,127,128,129,257,1024],group)))
        def reload():
            nonlocal db
            db.close();db=BlockStore(db_path,"filelist")
            hot=Hot()
            readers=[Observed(db,hot,b,n) for b in (63,128,256,1024) for n in (False,True)]
            stats["restarts"]+=1
            return hot,readers,len(history)
        def validate():
            incidence=defaultdict(set)
            for j,v in enumerate(history):
                for f in v:incidence[f].add(j)
            post=defaultdict(list)
            for j in range(fence,len(history)):
                for f in history[j]:post[f].append(j)
            true_hot={j for arr in post.values() for j in arr[-8:]}
            assert set(hot.live)==true_hot
            for h in readers:
                resident=set(true_hot)
                for (k,j),data in h.cache.items.items():
                    if k==EVENT:
                        assert unpack(data)==history[j]
                        resident.add(j)
                for (k,f),data in h.cache.items.items():
                    if k!=POST:continue
                    if data[0]!=EXCEPTION:assert set(expand(data))==incidence[f]
                    else:
                        n,excluded=parts(data)
                        assert n==len(incidence[f]) and set(excluded)<=incidence[f]
                        represented=set(excluded)|(resident&incidence[f])
                        if h.notify:assert represented==incidence[f]
                        else:assert represented<=incidence[f]
                    stats["resident_postings_checked"]+=1
                assert h.cache.size<=h.cache.limit
                if h.notify:assert not h.cache.pending and not h.cache.pending_bytes
        def lookup(f):
            freq=Counter(i for row in history[-32:] for i in row)
            all_ids={i for row in history for i in row}
            tie={i:freq[i] for i in all_ids}
            prior=sorted(all_ids,key=lambda i:(-freq[i],i))[:9]
            inc=[j for j,v in enumerate(history) if f in v]
            truth=Counter(g for j in inc for g in history[j])
            expected=sorted((g for g in all_ids if g!=f),key=lambda g:(-truth[g],-freq[g],g))[:8]
            for h in readers:
                rank,work=h.read(f,tie,prior,inc)
                assert rank==[(g,truth[g]) for g in expected]
                if h.notify:assert not work["guard_fallback"]
                stats["rank_checks"]+=1
            validate()
        def total_nested():return sum(c.nested_drops for c in readers)
        for j in range(128):
            ids=event(j);assert db.append(j,rev(j),ids);history.append(ids)
        hot,readers,fence=reload()
        for j in range(128,252):
            for f in (2,rng.choice((0,1,2,5,9,128,257,-1))):lookup(f)
            ids=event(j)
            if j in (128,145,201,230):
                before=list(db.db.execute("SELECT f,js FROM posting ORDER BY f"))
                try:db.append(j,rev(j),ids,fault=True)
                except RuntimeError:pass
                else:raise AssertionError("expected transaction rollback")
                assert list(db.db.execute("SELECT f,js FROM posting ORDER BY f"))==before
                assert db.next_id==len(history)
                stats["rollbacks"]+=1;lookup(ids[0])
            assert db.append(j,rev(j),ids);history.append(ids)
            old=set(hot.live)
            hints=possible_losses(hot,ids)
            hot.append(j,ids)
            assert (old-set(hot.live))=={i for i in hints if i not in hot.live}
            lost=[(i,hints[i]) for i in sorted(hints) if i not in hot.live]
            for h in readers:h.after_committed(j,ids,lost)
            if j%11==0:
                assert not db.append(j,rev(j),ids)
                try:db.append(j,rev(j+1000),ids)
                except ValueError:pass
                else:raise AssertionError("accepted a conflicting replay")
                stats["suppressed_duplicate"]+=1;stats["conflicts_rejected"]+=1
            validate()
            if j in (157,214):
                stats["recursive_event_drops"]+=total_nested()
                hot,readers,fence=reload();lookup(2)
        stats["recursive_event_drops"]+=total_nested()
        db.close()
    assert stats["recursive_event_drops"]>0
    return stats


if __name__=="__main__":
    parser=ArgumentParser();parser.add_argument("--verify",action="store_true");verify=parser.parse_args().verify
    result=dict(seed=60067,algebra=algebra(),drop_five=direct(),state_and_faults=stress())
    if verify:assert result==load(HERE/"audit.json")
    else:save(HERE/"audit.json",result)
    print(result)

"""Independently check optional packing bounds and replay archived witnesses on real SQLite."""
import argparse
from collections import Counter
from hashlib import sha1
from itertools import combinations
import json
from pathlib import Path
import random
import shutil
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(STUDY))
from decompose import components, load, panels, prepare, source
from value import bracket, gain
from checkpoint import Reader, Pinned, make_snapshot, persist

SEED = 580047


def brute_force_negative_values(rng):
    closed = 0
    for _ in range(250):
        n = rng.randrange(1, 10)
        ids = tuple(range(n))
        cost = {j:rng.randrange(1, 20) for j in ids}
        value = {j:rng.randrange(-140, 110) for j in ids}
        bonuses = Counter()
        for _ in range(rng.randrange(3*n)):
            group = frozenset(rng.sample(ids, rng.randint(1, n)))
            bonuses[group] += rng.randrange(1, 120)
        cap = rng.randrange(sum(cost.values())+1)
        feasible = [frozenset(t) for k in range(n+1) for t in combinations(ids, k)
                    if sum(cost[j] for j in t)<=cap]
        def objective(s):
            return sum(value[j] for j in s)+sum(v for q,v in bonuses.items() if s>=q)
        optional = max([0]+[objective(s)-100 for s in feasible if s])
        lo, hi, witness = bracket(cost, value, bonuses, cap)
        lower, upper = max(0, lo-100), max(0, hi-100)
        assert lower<=optional<=upper
        assert not witness or objective(set(witness))==lo
        closed += lower==upper
    return dict(instances=250,closed=closed)


def write_prefix(path, writes):
    writer = Reader(path, "shared", True)
    for _, j, sha, files in writes:
        assert writer.append(j, sha, files)
    writer.close()


def physical_subset(path, writes, ops, selected, cap, serialize_empty):
    n = len(writes)
    prepaid = 0
    if selected or serialize_empty:
        writer = Pinned(path, False)
        available = {j:writes[j][3] for j in selected}
        blob, kept, _ = make_snapshot(available,n,writes[-1][2],"recent",cap)
        assert kept==len(selected)
        persist(writer.db, blob)
        writer.close()
        reader = Pinned(path, True)
        assert not reader.rejected and set(reader.pinned)==set(selected)
        prepaid = len(blob)+reader.loaded_bytes+reader.receipt_bytes
    else:
        reader = Pinned(path, False)
    observed = Counter(prepaid=prepaid)
    count = 0
    for op in ops:
        if op[0]=="w":
            if count>=n:
                assert reader.append(*op[1:])
            count+=1
        elif count>=n:
            rank, work = reader.read(*op[1:4])
            if op[4] is not None:
                assert rank==op[4]
                observed["rank_checks"]+=1
            observed.update(posting=work[2],body=work[4],queries=1)
    reader.close()
    return observed


def synthetic_ops(seq):
    ops=[]
    freq=Counter()
    def query(f):
        prior=sorted(freq,key=lambda x:(-freq[x],x))[:9]
        ops.append(("q",f,freq.copy(),prior,None))
    for j, ids in enumerate(seq):
        anchors=[-1,0,0,1,2,128,257,0,128] if j%3==0 else [0,257]
        for f in anchors:query(f)
        ops.append(("w",j,sha1(str(j).encode()).hexdigest(),ids))
        freq.update(ids)
    for f in [0,1,2,0,0,-1,257]:query(f)
    return ops


def challenge_postings(directory, rng):
    fixtures=[
        ("all_subsets",[(0,1),(0,128),(2,257),(0,1),(0,128),(2,257)]*2),
        ("lost_after_repeat",[(0,1,128)]*64+[(0,2,257)]*72),
        ("mixed_varint_and_eviction",[tuple(rng.sample((0,1,2,127,128,257,1000),rng.randint(2,5)))
                                      for _ in range(268)])
    ]
    total=Counter()
    cases={}
    for label,seq in fixtures:
        ops=synthetic_ops(seq)
        prefix,costs,values,bonuses=components(ops)
        writes=[op for op in ops if op[0]=="w"][:len(prefix)]
        base=directory/"before.sqlite"
        write_prefix(base,writes)
        ids=sorted(costs)
        if len(ids)<=8:
            samples=[set(s) for k in range(len(ids)+1) for s in combinations(ids,k)]
        else:
            samples=[set(),set(ids)]+[set(rng.sample(ids,rng.randrange(len(ids)+1))) for _ in range(20)]
        assert not samples[0]
        cold=None
        meters=Counter()
        for s in samples:
            path=directory/"sample.sqlite"
            shutil.copyfile(base,path)
            actual=physical_subset(path,writes,ops,s,None,True)
            if cold is None:cold=actual
            assert gain(s,values,bonuses)==(cold["body"]-actual["body"],cold["posting"]-actual["posting"])
            meters.update(subsets=1,post_queries=actual["queries"])
            path.unlink()
        base.unlink()
        cases[label]=dict(meters)
        total.update(meters)
    return dict(total=dict(total),fixtures=cases)


def replay_witnesses(directory):
    fixed=load(STUDY/"results.json")["cases"]
    natural=load(STUDY/"natural-results.json")["projects"]
    original=panels()
    external={g:source(g)[0] for g in ("replication","seed_pair")}
    by_group={}
    projects=set()
    total=Counter()
    for key,fix in fixed.items():
        group,schedule,repo=key.split("/",2)
        projects.add(repo)
        rows=(original[schedule] if group=="original" else external[group])[repo]
        ops,_=prepare(rows,schedule)
        net=natural[group+"-"+schedule+"/"+repo]
        events=[o for o in ops if o[0]=="w"]
        writes=events[:len(events)//2]
        base=directory/"before.sqlite"
        write_prefix(base,writes)
        tally=Counter(cases=1,fixed_closed=int(fix["lo"]==fix["hi"]),
                      optional_closed=int(net["lower"]==net["upper"]))
        for mode,selected in (("fixed",fix["chosen"]),("optional",net["witness"])):
            path=directory/"sample.sqlite"
            shutil.copyfile(base,path)
            fixed_mode=mode=="fixed"
            actual=physical_subset(path,writes,ops,selected,1024 if fixed_mode else None,fixed_mode)
            assert actual["rank_checks"]==actual["queries"]==fix["post"]
            gross=net["cold"]-actual["body"]-actual["posting"]
            if fixed_mode:
                assert gross==fix["lo"]
                tally["verified_fixed_gross"]+=gross
            else:
                assert gross-actual["prepaid"]==net["lower"]
                tally["verified_optional_net"]+=gross-actual["prepaid"]
            tally.update(sqlite_runs=1,rank_checks=actual["rank_checks"])
            path.unlink()
        base.unlink()
        total.update(tally)
        by_group.setdefault(group+"/"+schedule,Counter()).update(tally)
    return dict(total=dict(total),unique_repositories=len(projects),groups=by_group)


def compute():
    rng=random.Random(SEED)
    # A single deterministic RNG stream matches the original, externally run audit.
    brute=brute_force_negative_values(rng)
    with TemporaryDirectory(dir=HERE,prefix="audit-sqlite-") as tmp:
        root=Path(tmp)
        stress=challenge_postings(root,rng)
        physical=replay_witnesses(root)
        assert not list(root.iterdir())
    return dict(seed=SEED,random_generator="Python random.Random, shared sequential stream",
                commands=dict(generate="python -B verify_value.py",verify="python -B verify_value.py --verify"),
                optional_brute_force=brute,subset_identity=stress,real_witnesses=physical)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    data=compute()
    path=HERE/"audit.json"
    if verify:
        assert data==json.loads(path.read_bytes()),"Independent audit disagrees with saved counters."
    else:
        path.write_bytes((json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode("utf-8"))
    print(json.dumps({"optional_brute_force":data["optional_brute_force"],
                      "subset_identity":data["subset_identity"]["total"],
                      "real_witnesses":data["real_witnesses"]["total"]}))


if __name__=="__main__":
    main()

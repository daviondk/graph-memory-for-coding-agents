"""Join fixed native component outputs to an independent byte/range audit; cluster by issue."""
from collections import defaultdict

import numpy as np

from project import D, digest, read, save


def evaluate(*, keys, cases, reference, native, predicate):
    paired=defaultdict(list)
    blocks = file_closed = read_bytes = closed_bytes = new_key_hits = old_active = 0
    duplicates, strict_wins, strict_losses = 0, 0, 0
    for key in keys:
        row,ref,db=cases[key],reference[key],native[key]
        closed=set(db["closed_slots"])
        assert db["closed_slots"] == predicate[key]
        assert closed == {b["slot"] for b in row["chosen"] if b["path"]==row["changed"]}
        assert db["blocks"] == len(row["chosen"])
        assert db["closed_bytes"] == sum(b["bytes"] for b in row["chosen"] if b["slot"] in closed)
        assert db["edge_count"] == len(closed)
        assert int(not closed) == ref["file_reuse"]
        flag=int(not closed)
        paired[row["issue"]].append([flag,ref["range_reuse"],ref["strict_range"]])
        delta=ref["strict_range"]-flag
        strict_wins+=int(delta>0);strict_losses+=int(delta<0)
        duplicates+=int(len(row["chosen"])>len(set(b["path"] for b in row["chosen"])))
        file_closed+=len(closed);blocks+=db["blocks"];closed_bytes+=db["closed_bytes"]
        read_bytes+=sum(b["bytes"] for b in row["chosen"])
        new_key_hits+=db["new_intent_old_key_hits"];old_active+=db["old_active"]
    arr=[np.asarray(v) for _,v in sorted(paired.items())]
    totals=np.stack([x.sum(0) for x in arr]);counts=np.array([len(x) for x in arr])
    macro=totals/counts[:,None];rng=np.random.default_rng(405508)
    weights=np.stack([np.bincount(a,minlength=len(arr)) for a in rng.integers(len(arr),size=(10000,len(arr)))])
    differences=totals[:,2]-totals[:,0];norm=macro[:,2]-macro[:,0]
    delta=(weights@differences)/(weights@counts);macro_draws=weights@norm/len(arr)
    return dict(n=len(keys),issues=len(arr),db_active_packets=int(totals[:,0].sum()),
           range_same_packets=int(totals[:,1].sum()),strict_range_packets=int(totals[:,2].sum()),
           micro_delta=float(differences.sum()/counts.sum()),
           micro_ci=np.quantile(delta,[.025,.975]).tolist(),macro_delta=float(norm.mean()),
           macro_ci=np.quantile(macro_draws,[.025,.975]).tolist(),
           strict_wins=strict_wins,strict_losses=strict_losses,
           block_occurrences=blocks,closed_block_occurrences=file_closed,old_active=old_active,
           selected_bytes=read_bytes,closed_bytes=closed_bytes,new_intent_old_key_hits=new_key_hits,
           multi_block_same_path_events=duplicates)


def main():
    cases=read(D/"cases.json.gz");reference=read(D/"comparison-reference.json.gz")
    predicate=read(D/"predicate.json.gz");db=read(D/"native-projections.json.gz")
    run=read(D/"native-run.json");pilot=read(D/"pilot-decision.json")
    assert digest(D/"native-projections.json.gz")==run["projected_sha256"]
    assert digest(D/"predicate.json.gz")==run["predicate_sha256"]
    assert set(cases)==set(reference)==set(predicate)
    assert all((not predicate[k])==bool(reference[k]["file_reuse"]) for k in predicate)
    assert len(db)==(len(cases) if pilot["qualified"] else 64)
    result={}
    for group in ("main","additional","all"):
        keys=[k for k in db if group=="all" or cases[k]["group"]==group]
        result[group]=evaluate(keys=keys,cases=cases,reference=reference,native=db,predicate=predicate)
    save("results.json",dict(groups=result,bootstrap=dict(unit="issue",replicates=10000,seed=405508),
                             native_seal=digest(D/"native-run.json"),reference=digest(D/"comparison-reference.json.gz")))
    print({m:[v["n"],v["db_active_packets"],v["strict_range_packets"],v["closed_bytes"]] for m,v in result.items()})


if __name__=="__main__":
    main()


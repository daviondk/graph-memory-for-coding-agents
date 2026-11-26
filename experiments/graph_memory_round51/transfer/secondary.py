"""Secondary comparison against unconditional graph traversal and descriptive task-type strata."""
import numpy as np
from study import D, get, put, sha


def main():
    rows = get(D/"outcomes.json.gz")
    ctx = get(D/"contexts.json.gz")
    costs = {r[0]:r for r in get(D/"timing-events.json.gz") if not r[1]}
    summary = {}
    for name, subset in [("all",sorted(rows))]+[(kind,sorted(q for q,r in rows.items() if r["kind"]==kind))
                                                 for kind in sorted({r["kind"] for r in rows.values()})]:
        res = {}
        for arm in ("dense","adaptive","linked_dense"):
            vals = [rows[q]["arms"][arm] for q in subset]
            refs = [ctx[q]["refs"][arm] for q in subset]
            events = [costs[k] for i,k,t in refs]
            res[arm] = dict(n=len(subset),metrics=(100*np.mean(vals,axis=0)).tolist(),switches=sum(i!=ctx[q]["refs"]["dense"][0] for q,(i,k,t) in zip(subset,refs,strict=True)),
                prompt_tokens=sum(t for i,k,t in refs),attributed_decode_ms=sum(e[4] for e in events),attributed_total_ms=sum(e[6] for e in events),decoded_tokens=sum(e[5] for e in events))
        summary[name]=res
    qids=sorted(rows)
    delta=np.array([np.array(rows[q]["arms"]["adaptive"])-rows[q]["arms"]["linked_dense"] for q in qids])
    rng = np.random.default_rng(470091)
    samples = [delta[rng.integers(len(qids),size=(100,len(qids)))].mean(axis=1) for _ in range(100)]
    ci = 100*np.quantile(np.concatenate(samples),[.025,.975],axis=0).T
    put(D/"secondary.json",dict(source=sha(D/"outcomes.json.gz"),timings=sha(D/"timing-events.json.gz"),strata=summary,
        gate_minus_always=dict(pp=(100*delta.mean(0)).tolist(),ci=ci.tolist(),wins=(delta>1e-12).sum(0).tolist(),losses=(delta< -1e-12).sum(0).tolist())))
    print("Secondary gate-minus-always",100*delta.mean(0),ci)
    print(summary)


if __name__=="__main__":
    main()

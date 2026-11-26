"""Score frozen maps using only the next visible numbered view."""
from collections import Counter, defaultdict
import json
import numpy as np
from forecast import ROOT, NAMES, read, save, sha


def tally(rows, target, steps):
    present = [(n, s, origin) for n, s, origin in rows if n in target]
    correct = [(n, origin) for n, s, origin in present if target[n] == s]
    provenance = Counter("initial" if t == 0 else "latest" if t == steps else "intermediate"
                         for _, t in correct)
    return dict(observed=len(target), correct=len(correct), wrong=len(present)-len(correct),
                unchecked=len(rows)-len(present), stored=len(rows), correct_by_origin=dict(provenance))


def evaluate(forecasts, targets):
    out = []
    assert forecasts.keys() == targets.keys()
    for key, item in forecasts.items():
        target = dict(targets[key]["rows"])
        assert target and len(target) == len(targets[key]["rows"])
        states = item["states"]
        steps = len(item["operations"])
        metrics = {m: tally(states[m], target, steps) for m in NAMES}
        assert metrics["H"]["stored"] == metrics["Tstar"]["stored"]
        assert metrics["T"]["correct_by_origin"].get("latest", 0) == metrics["F"]["correct"]
        out.append({k: v for k, v in item.items() if k not in ("states", "sizes")} |
                   dict(key=key, metrics=metrics, native_audits=targets[key]["native_audits"]))
    return out


def summarize(rows):
    if not rows:
        return {"episodes": 0}
    issues = sorted({r["issue"] for r in rows})
    issue_idx = {key: i for i, key in enumerate(issues)}
    mat = np.zeros((len(issues), len(NAMES), 5), dtype=np.int64)
    origins = Counter()
    for r in rows:
        for j, m in enumerate(NAMES):
            mat[issue_idx[r["issue"]], j] += [r["metrics"][m][k] for k in
                ("observed", "correct", "wrong", "unchecked", "stored")]
        origins.update(r["metrics"]["T"]["correct_by_origin"])
    rates = mat[:, :, 1:3] / mat[:, :, 0, None]
    means = rates.mean(0)
    totals = mat.sum(0)
    methods = {}
    for j, m in enumerate(NAMES):
        n, c, w, u, s = totals[j].tolist()
        methods[m] = dict(observed=n, correct=c, wrong=w, unchecked=u, avg_slots=s/len(rows),
                          coverage=means[j, 0], stale=means[j, 1],
                          pooled_precision=c/(c+w) if c+w else None)
    chosen = np.random.default_rng(370541).integers(len(issues), size=(10000, len(issues)))
    comparisons = {}
    for a, b in (("T", "F"), ("T","K"), ("Tstar","H"), ("T","C")):
        d = rates[:,NAMES.index(a)] - rates[:,NAMES.index(b)]
        ci = np.quantile(d[chosen].mean(1), [.025,.975], axis=0) if len(issues)>1 else None
        comparisons[a+"-"+b] = {k: dict(delta=d[:,j].mean(), ci95=ci[:,j].tolist() if ci is not None else None,
            plus=int((d[:,j]>0).sum()), equal=int((d[:,j]==0).sum()), minus=int((d[:,j]<0).sum()))
                                 for j, k in enumerate(("coverage","stale"))}
    audits = [a for r in rows for a in r["native_audits"]]
    return dict(episodes=len(rows), issues=len(issues), runs=len({r["rid"] for r in rows}),
                repos=sorted({r["repo"] for r in rows}), length=Counter(len(r["operations"]) for r in rows),
                any_shift=sum(any(r["shifts"]) for r in rows),
                anchors=sum(sum(r["anchors"]) for r in rows), operations=len(audits),
                native_verified=sum(a["native_full_verified"] for a in audits),
                native_anchor_agrees=sum(a["native_anchor_agrees"] is True for a in audits),
                native_anchor_disagrees=sum(a["native_anchor_agrees"] is False for a in audits),
                transfer_correct_by_origin=dict(origins), methods=methods, contrasts=comparisons)


def main():
    seal=read(ROOT/"forecast-seal.json")
    assert sha(ROOT/"forecasts.json.gz")==seal["forecasts"] and sha(ROOT/"targets.json.gz")==seal["targets"]
    rows=evaluate(read(ROOT/"forecasts.json.gz"), read(ROOT/"targets.json.gz"))
    groups={a+"_"+b:summarize([r for r in rows if (r["cohort"],r["window"])==(a,b)])
            for a in ("main","secondary") for b in ("strict","opaque")}
    primary=[r for r in rows if (r["cohort"],r["window"])==("main","strict")]
    per_issue={issue:summarize([r for r in primary if r["issue"]==issue])
               for issue in sorted({r["issue"] for r in primary})}
    save("results.json", dict(groups=groups, primary_by_issue=per_issue,
         outcomes=save("outcomes.json.gz",rows), forecast_seal=sha(ROOT/"forecast-seal.json"), numpy=np.__version__))
    for name,g in groups.items():
        print(name,g["episodes"],g["issues"],g["runs"],g["repos"],g["length"],"shifts",g["any_shift"],g["anchors"],g["operations"],g["native_anchor_agrees"])
        print(g["transfer_correct_by_origin"])
        print([(m,round(v["coverage"]*100,2),v["correct"],v["wrong"],round(v["avg_slots"],2)) for m,v in g["methods"].items()])
        print([(k,round(v["coverage"]["delta"]*100,2),[round(n*100,2) for n in v["coverage"]["ci95"]],v["coverage"]["plus"],v["coverage"]["minus"]) for k,v in g["contrasts"].items()])


if __name__=="__main__":
    main()

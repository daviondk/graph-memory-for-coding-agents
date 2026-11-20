"""Exploratory matched-count random control, conditional on fold and empty history."""
import collections
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent

if __name__=="__main__":
    def lines(name):
        return [json.loads(l) for l in (ROOT/name).read_text().splitlines()]
    states={(r["dataset"],r["id"]):r for r in lines("potential_outcomes.jsonl")}
    decisions=collections.defaultdict(list)
    for r in lines("decisions.jsonl"):
        decisions[r["evaluation"]].append(r)
    out={}
    for name,rows in decisions.items():
        ds=name.split("_")[-1] if "_to_" in name else name.split("_")[0]
        n=len(rows)
        strata=collections.defaultdict(list)
        baseline=0
        real=0
        for r in rows:
            item=states[ds,r["id"]]
            off,on=[item[a]["grades"][0] for a in ["off","on"]]
            baseline+=off
            real+=item[r["action"]]["grades"][0]
            strata[r["fold"],bool(item["features"][2])].append((on-off,r["action"]=="on"))
        rng=np.random.default_rng(20261119)
        total=np.full(50000,baseline,dtype=float)
        expected=baseline
        for stratum in sorted(strata):
            z=np.array(strata[stratum])
            gain=z[:,0]
            times=int(z[:,1].sum())
            expected+=times*gain.mean()
            if times==len(gain):
                total+=gain.sum()
                continue
            if times:
                for start in range(0,len(total),1000):
                    order=np.argsort(rng.random((1000,len(gain))),axis=1)[:,:times]
                    total[start:start+1000]+=gain[order].sum(axis=1)
        out[name]={"observed":real/n,"matched_random_expected":expected/n,"observed_minus_expected":(real-expected)/n,
                   "randomization_band":(np.quantile(total,[.025,.975])/n).tolist(),
                   "fraction_random_at_least_observed":float(np.mean(total>=real-1e-10)),"replicates":len(total)}
    print(json.dumps(out,indent=2))
    fn=ROOT/"count_control.json"
    if fn.exists():
        assert json.loads(fn.read_bytes())==out
    else:
        fn.write_text(json.dumps(out,indent=2),encoding='utf8')

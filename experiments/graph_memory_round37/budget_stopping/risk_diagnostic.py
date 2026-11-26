"""Post hoc split diagnostics. The beta-binomial integrates calibration-quantile uncertainty."""
from collections import Counter
from scipy.stats import betabinom
from policy import D, load, math, np, save

def diagnose():
    stage = {s:load(D/(s+"-outcomes.json.gz")) for s in ("dev","test")}
    freq = {s:Counter(r["t"] for r in rows.values()) for s,rows in stage.items()}
    size = {s:dict(sorted(Counter(c.values()).items())) for s,c in freq.items()}
    ref = load(D/"test-results.json")
    m,n = (len(freq[s]) for s in ("dev","test"))
    models = {}
    for key,measures in ref["means"].items():
        if "_" not in key:
            continue
        alpha = int(key.split("_")[1])/100
        rank = math.ceil((m+1)*(1-alpha))
        # Under exchangeability with continuous scores, #scores exceeding calibration order statistic
        # has beta-binomial law. Ties / rounding upward can reduce actual failure counts.
        tail = betabinom(n,m+1-rank,rank)
        observed = measures["trajectories_hurt"]
        by_size = {}
        for s,rows in stage.items():
            sets = {}
            for record in rows.values():
                t = record["t"]
                sets[t] = bool(sets.get(t,False) or record["arms"][key][4])
            bins = {}
            for t,hurt in sets.items():
                grp = str(min(freq[s][t],4))
                pair = bins.setdefault(grp,[0,0])
                pair[0] += int(hurt)
                pair[1] += 1
            by_size[s] = bins
        models[key] = dict(nominal_rank=rank,exchangeable_count_interval=tail.ppf([.025,.975]).astype(int).tolist(),
                           upper_tail_bound=float(tail.sf(observed-1)),by_group_size=by_size)
    save("risk-diagnostic.json",dict(calibration=m,evaluation=n,cluster_size_distribution=size,models=models))
    print(models["learned_5"])
if __name__=="__main__":
    diagnose()


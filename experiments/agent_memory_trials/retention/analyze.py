"""Pre-specified paired contrasts of within-world outcomes. Python stdlib only."""
import csv
import gzip
import json
import math
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

from experiment import BASELINES, CONDITIONS, HERE, POLICIES, TOOLS, WORLDS, verify_seal

METRICS = ("required_reads", "actual_reads", "returned_values", "correct")


def critical(p, df):
    def cosine_int(angle):
        # df=63. Integral cos(theta) ** (df-1) from zero to angle.
        assert df % 2 == 1
        total = angle
        for n in range(2, df, 2):
            total = math.sin(angle) * math.cos(angle)**(n-1) / n + (n-1) / n * total
        return total
    full = cosine_int(math.pi / 2)
    lo, hi = 0., 20.
    for _ in range(60):
        mid = (lo+hi)/2
        quantile = .5 + cosine_int(math.atan(mid / math.sqrt(df))) / (2*full)
        if quantile < p:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


T95 = critical(.975, len(WORLDS)-1)
T_FAMILY = critical(1-.05/(2*16), len(WORLDS)-1)


def describe(values):
    m, sd = st.mean(values), st.stdev(values)
    se = sd / math.sqrt(len(values))
    return dict(mean=m, sd=sd, median=st.median(values), min=min(values), max=max(values),
                world_n=len(values), wins=sum(x>0 for x in values), ties=sum(x==0 for x in values),
                lower95=m-T95*se, upper95=m+T95*se)


def bootstrap(values):
    rng = random.Random(833171)
    ordered = sorted(st.fmean(rng.choices(values,k=len(values))) for _ in range(10000))
    return [ordered[249], ordered[9749]]


def write_json(path, obj):
    path.write_bytes((json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def analyze(folder):
    grouped = defaultdict(Counter)
    examples = {}
    coloc = defaultdict(list)
    with gzip.open(folder/"jobs.csv.gz","rt",encoding="utf-8",newline="") as handle:
        for row in csv.DictReader(handle):
            if row["phase"] == "test":
                keys = list(map(int,row["role_ordered_keys"].split(".")))
                pairs = [(a,b) for i,a in enumerate(keys) for b in keys[i+1:]]
                coloc[int(row["seed"]),int(row["rho"])].append(st.mean(a//4==b//4 for a,b in pairs))
    with gzip.open(folder/"steps.csv.gz","rt",encoding="utf-8",newline="") as handle:
        joint_rows = {}
        for row in csv.DictReader(handle):
            seed, rho, tool, name, step = (int(row["seed"]), int(row["rho"]), row["tool"],
                                          row["policy"], int(row["step"]))
            bucket = grouped[seed,rho,tool,name]
            bucket["n"] += 1
            for metric in METRICS:
                bucket[metric] += int(row[metric])
            if tool == "block":
                if name == "joint":
                    joint_rows[step] = row
                if name == "validation_choice":
                    joint = joint_rows[step]
                    assert (joint["seed"],joint["rho"],joint["step"]) == (row["seed"],row["rho"],row["step"])
                    category = (joint["correct"],row["correct"])
                    label = {"10":"joint_completes","01":"baseline_completes","00":"neither_completes"}.get("".join(category))
                    if label and label not in examples:
                        examples[label] = dict(joint=joint,validation_choice=row)
    assert len(grouped) == len(WORLDS)*len(CONDITIONS)*len(TOOLS)*len(POLICIES)
    assert all(b["n"] == 128 for b in grouped.values())
    val = {}
    with (folder/"worlds.csv").open("w",encoding="utf-8",newline="") as handle:
        w = csv.writer(handle,lineterminator="\n")
        w.writerow(["seed","rho","tool","policy","jobs"]+list(METRICS))
        for (seed,rho,tool,name), bucket in sorted(grouped.items()):
            values = [bucket[m]/bucket["n"] for m in METRICS]
            w.writerow([seed,rho,tool,name,bucket["n"]]+values)
            for metric,x in zip(METRICS,values):
                val[seed,rho,tool,name,metric] = x
    for seed in WORLDS:
        for tool in TOOLS:
            for name in POLICIES:
                for m in METRICS:
                    val[seed,"all",tool,name,m] = st.mean(val[seed,rho,tool,name,m] for rho in CONDITIONS)
    def differences(tool, rho, name, m):
        # Positive = improvement in joint. For success higher is better.
        sign = 1 if m == "correct" else -1
        return [sign*(val[s,rho,tool,"joint",m]-val[s,rho,tool,name,m]) for s in WORLDS]
    estimates = []
    contrasts = []
    for tool in TOOLS:
        for rho in ("all",)+CONDITIONS:
            for m in METRICS:
                for name in POLICIES:
                    row = dict(tool=tool,rho=rho,policy=name,metric=m)
                    estimates.append(row | describe([val[s,rho,tool,name,m] for s in WORLDS]))
                    if name == "joint":
                        continue
                    diffs = differences(tool,rho,name,m)
                    result = row | describe(diffs)
                    if tool == "block" and m == "required_reads":
                        half = T_FAMILY*result["sd"]/math.sqrt(len(WORLDS))
                        result.update(family_lower95=result["mean"]-half,family_upper95=result["mean"]+half)
                    contrasts.append(result)
    interactions = []
    for name in BASELINES:
        for metric in METRICS:
            low,high = (differences("block",rho,name,metric) for rho in (0,100))
            interactions.append(dict(baseline=name,metric=metric) | describe([b-a for a,b in zip(low,high)]))
    strength = {}
    for tool in TOOLS:
        for rho in ("all",)+CONDITIONS:
            strength[tool+"_"+str(rho)] = min(BASELINES,key=lambda b: st.mean(val[s,rho,tool,b,"required_reads"] for s in WORLDS))
    choices = Counter((x["tool"],x["validation_choice"]) for x in json.loads((folder/"builds.json").read_bytes()))
    write_json(folder/"summary.json", dict(estimates=estimates,contrasts_positive_favor_joint=contrasts,
                strongest_reference_descriptive=strength,interaction_high_minus_low=interactions,
                validation_choices={str(k):v for k,v in sorted(choices.items())},n_worlds=len(WORLDS),
                test_jobs=len(WORLDS)*len(CONDITIONS)*128,
                step_rows=sum(b["n"] for b in grouped.values()),
                co_location_by_rho={str(r):describe([st.mean(coloc[s,r]) for s in WORLDS]) for r in CONDITIONS},
                primary_bootstrap95=bootstrap(differences("block","all","validation_choice","required_reads")),
                t_critical_95=T95,t_critical_16_family=T_FAMILY))
    write_json(folder/"examples.json", examples)


if __name__ == "__main__":
    verify_seal()
    analyze(Path(sys.argv[1]) if len(sys.argv)>1 else HERE/"results")

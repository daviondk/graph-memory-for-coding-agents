import argparse
import gzip
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from clock import CLOCKS, HALVES, HERE, STATIC, evaluate
from prepare import dump

def score(ranked, targets):
    indices = [i+1 for i,b in enumerate(ranked) if b in targets]
    return [len(indices)/len(targets), int(1 in indices), 1/min(indices) if indices else 0]

def grouped(rows):
    by_repo = defaultdict(list)
    for row in rows:
        by_repo[row["repo"]].append(row)
    repos = {}
    for repo, part in sorted(by_repo.items()):
        models = part[0]["ranked"]
        means = {}
        for model in models:
            vals = [score(r["ranked"][model],r["targets"]) for r in part]
            means[model] = list(map(statistics.fmean,zip(*vals)))
        reachable = statistics.fmean(r["reachable"]/len(r["targets"]) for r in part)
        repos[repo] = {"n":len(part),"means":means,"reachable":reachable}
    macro = {m:list(map(statistics.fmean,zip(*(x["means"][m] for x in repos.values()))))
             for m in next(iter(repos.values()))["means"]}
    return repos,macro

def contrast(repos, experiment, control):
    diffs = [v["means"][experiment][0]-v["means"][control][0] for v in repos.values()]
    wins = sum(d>1e-12 for d in diffs)
    losses = sum(d< -1e-12 for d in diffs)
    n = wins+losses
    rng = random.Random(55013)
    samples = sorted(statistics.fmean(rng.choices(diffs,k=len(diffs))) for _ in range(20000))
    p = min(1, 2*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/2**n)
    return dict(control=control,delta=statistics.fmean(diffs),interval=[samples[499],samples[19499]],
                signs=[wins,len(diffs)-n,losses],sign_p=p)

def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("panel", choices=["development","external"])
    panel = parser.parse_args().panel
    events = json.loads(gzip.decompress((HERE/(panel+"-events.json.gz")).read_bytes()))
    lock = HERE/"selection.json"
    if panel == "development":
        models = list(STATIC)+[f"{c}_{h}" for c in CLOCKS for h in HALVES]
    else:
        spec = json.loads(lock.read_bytes())
        for name, value in spec["hashes"].items():
            assert fingerprint(HERE/name) == value
        models = list(STATIC)+list(spec["clocks"].values())
    rows = [row for repo,history in events.items() for row in evaluate(repo,history,models)]
    by_repo, macro = grouped(rows)
    # Compact rank paths via a lossless per-project dictionary.
    paths = {name:sorted({p for _,t,d in stream for p in t+d}) for name,stream in events.items()}
    lookup = {repo:{p:i for i,p in enumerate(li)} for repo,li in paths.items()}
    converted = []
    for r in rows:
        index = lookup[r["repo"]]
        converted.append({**r,"anchor":index[r["anchor"]],"targets":[index[x] for x in r["targets"]],
                          "ranked":{m:[index[x] for x in ranks] for m,ranks in r["ranked"].items()}})
    dump(HERE/(panel+"-ranks.json.gz"), dict(paths=paths,rows=converted))
    if panel == "development":
        best = {c:max([f"{c}_{h}" for h in HALVES],key=lambda m:macro[m][0]) for c in CLOCKS}
        controls = list(STATIC)+[best[c] for c in CLOCKS if c != "xor"]
        control = max(controls, key=lambda m:macro[m][0])
        names = ("PROTOCOL_RU.md","clock.py","evaluate.py","development-events.json.gz","external-pins.json")
        frozen = {"clocks":best,"control":control,"hashes":{n:fingerprint(HERE/n) for n in names}}
        if lock.exists():
            assert json.loads(lock.read_bytes()) == frozen
        dump(lock,frozen)
        print(best,control,flush=True)
    else:
        best, control = spec["clocks"],spec["control"]
    summary = dict(n=len(rows),repos=by_repo,macro=macro,
                   no_queries=sorted(set(events)-set(by_repo)),
                   primary=contrast(by_repo,best["xor"],control),
                   columns=["Recall@5","Hit@1","MRR@5"])
    dump(HERE/(panel+"-results.json"),summary)
    print(panel,len(rows), {m:round(macro[m][0],4) for m in list(STATIC)+list(best.values())},summary["primary"])

if __name__=="__main__":
    main()

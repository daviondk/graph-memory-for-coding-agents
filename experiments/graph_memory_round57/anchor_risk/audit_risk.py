"""Independent reference for the primary pair, using complete past posting lists and exact fractions."""
from collections import Counter, defaultdict
from fractions import Fraction
from math import isclose
from pathlib import Path
import json

from evaluate_risk import HERE, read


def check(stream, decisions):
    names = {}
    all_members = []
    path_history = defaultdict(list)
    recent_commits = []
    records = {r["t"]: r for r in decisions}
    cases = changed = 0
    totals = Counter()
    for t,(sha,raw) in enumerate(stream):
        fs = raw if len(raw) <= 64 else []
        if t in records:
            row = records[t]
            assert t >= len(stream)//2 and row["sha"] == sha
            gold = [names.get(p,-1) for p in fs]
            assert gold == row["ids"]
            freq = Counter(i for past in recent_commits[-32:] for i in past)
            commit_total = Counter()
            for seed in gold:
                events = [j for j in path_history[seed] if any(j in path_history[b][-8:] for b in all_members[j])]
                events = sorted(events,key=lambda j:(len(all_members[j])>6,-j))[:8]
                answer = row["answers"][str(seed)]
                reads,members,idx = answer["readers"]["fill6"]
                assert reads == len(events) and members == sum(len(all_members[j]) for j in events)
                results = {}
                for pos,mode in [(1,"companion"),(2,"commit")]:
                    scores = Counter()
                    for j in events:
                        event = all_members[j]
                        den = len(event)-1
                        if mode == "commit":
                            den *= len(event)
                        for target in event:
                            scores[target] += Fraction(1,den)
                    rank = sorted((i for i in range(len(names)) if i!=seed),key=lambda i:(-scores[i],-freq[i],i))[:8]
                    assert rank == answer["packets"][idx[pos]]
                    commit_total[mode] += len(set(rank).intersection(gold))
                    results[mode] = rank
                cases += 1
                changed += results["companion"] != results["commit"]
            for mode,numerator in commit_total.items():
                totals[mode] += Fraction(numerator,len(gold)*(len(gold)-1))
        codes = [names.setdefault(p,len(names)) for p in fs]
        recent_commits.append(codes)
        if len(codes) >= 2:
            j = len(all_members)
            all_members.append(codes)
            for i in codes:
                path_history[i].append(j)
    assert len(records) == sum(i>=len(stream)//2 and 2<=len(paths)<=64 for i,(_,paths) in enumerate(stream))
    return cases, changed, {mode:float(v/len(records)) for mode,v in totals.items()}


def main():
    streams = read(HERE.parent/"replication"/"events.json.gz")
    ranks = read(HERE/"new-ranks.json.gz")
    published = read(HERE/"new-metrics.json")["new"]["projects"]
    cases = changed = 0
    for repo,rows in streams.items():
        n,d,values = check(rows,ranks[repo])
        for mode,value in values.items():
            assert isclose(value,published[repo]["methods"]["fill6/"+mode]["commit_recall"],abs_tol=1e-12)
        cases += n
        changed += d
    result = {"queries":cases,"rankings":cases*2,"changed":changed,"projects":len(streams)}
    print(result)
    (HERE/"audit.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")


if __name__ == "__main__":
    main()

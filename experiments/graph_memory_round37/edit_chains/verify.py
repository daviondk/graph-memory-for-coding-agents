"""Check signed files, map-level constraints, and independently recompute all row counts."""
import argparse
import sys
import tempfile
from collections import Counter
from forecast import CAP, EXPECTED, NAMES, ROOT, SOURCE, predict, read, save, sha

FILES = ("PROTOCOL_RU.md", "REPORT_RU.md", "REPRODUCE_RU.md", "forecast.py", "score.py",
         "verify.py", "forecast-seal.json", "forecasts.json.gz", "targets.json.gz",
         "outcomes.json.gz", "results.json", "checks.json")


def toy():
    def edit(k, old, shift, rows):
        return {"k": k, "old_breaks": old, "delta": shift, "rows": rows}
    first = [(1, "a"), (4, "d"), (9, "i")]
    # First change deletes original line 4 and moves 9 to 11; second change shifts 11 to 10.
    changes = [edit(4, 0, 2, [(4, "NEW"), (6, "middle")]),
               edit(7, 1, -1, [(7, "last")])]
    maps, _ = predict("p", first, changes)
    assert maps["T"] == [[1,"a",0],[4,"NEW",1],[6,"middle",1],[7,"last",2],[10,"i",0]]
    assert maps["F"] == [[7, "last", 2]]
    assert maps["C"] == [[4,"NEW",1],[6,"middle",1],[7,"last",2]]
    unknown = edit(None, 0, -1, [(5,"uncertain")])
    final, _ = predict("p", first, changes + [unknown])
    assert final["T"] == final["C"] == final["F"] == [[5, "uncertain", 3]]
    large = [(i, str(i)) for i in range(1,401)]
    latest = [(i, "new"+str(i)) for i in range(900,1100)]
    a, sizes = predict("p", large, [edit(999,0,0,latest), edit(1000,0,0,latest)])
    b, _ = predict("p", large[::-1], [edit(999,0,0,latest[::-1]), edit(1000,0,0,latest[::-1])])
    assert a == b and all(n == CAP for step in sizes for n in step.values())


def verify():
    toy()
    seal = read(ROOT/"forecast-seal.json")
    assert sha(SOURCE/"events.json.gz") == EXPECTED == seal["input"]
    assert sha(ROOT/"PROTOCOL_RU.md") == seal["protocol"]
    assert sha(ROOT/"forecast.py") == seal["predictor"]
    assert sha(ROOT/"forecasts.json.gz") == seal["forecasts"]
    assert sha(ROOT/"targets.json.gz") == seal["targets"]
    forecasts, targets = read(ROOT/"forecasts.json.gz"),read(ROOT/"targets.json.gz")
    result = read(ROOT/"results.json")
    assert result["forecast_seal"] == sha(ROOT/"forecast-seal.json")
    assert result["outcomes"] == sha(ROOT/"outcomes.json.gz")
    outcomes = {r["key"]:r for r in read(ROOT/"outcomes.json.gz")}
    assert forecasts.keys() == targets.keys() == outcomes.keys()
    counts, bound = Counter(), Counter()
    for key,row in forecasts.items():
        truth = set(map(tuple,targets[key]["rows"]))
        addresses = {n for n,_ in truth}
        steps = len(row["operations"])
        assert len(addresses)==len(truth) and steps>=2 and len(row["sizes"])==steps
        for step in row["sizes"]:
            assert step["H"]==step["Tstar"] and max(step.values())<=CAP
            bound["updates"]+=1
        for name in NAMES:
            state=row["states"][name]
            pred = {(n,s) for n,s,_ in state}
            assert len(pred)==len(state)==len({n for n,_ in pred})==row["sizes"][-1][name]
            new = {(n,s) for n,s,t in state if t==steps}
            last = {(n,s) for n,s,_ in row["states"]["F"]}
            assert new==last
            common=pred & truth
            stale=sum(n in addresses for n,s in pred-common)
            x=outcomes[key]["metrics"][name]
            assert (len(truth),len(common),stale,len(pred))==(x["observed"],x["correct"],x["wrong"],x["stored"])
            counts[(row["cohort"]+"_"+row["window"],name,"correct")] += len(common)
            counts[(row["cohort"]+"_"+row["window"],name,"wrong")] += stale
            bound["maps"]+=1
    for (group,method,metric), value in counts.items():
        assert result["groups"][group]["methods"][method][metric]==value
    return dict(episodes=len(forecasts), maps=bound["maps"], step_capacity_matches=bound["updates"],
                fixtures=["two_signed_shifts","unanchored_fallback","overflow_and_reordered_input"],
                source=EXPECTED)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--seal",action="store_true")
    args=parser.parse_args()
    checks=verify()
    if args.seal:
        save("checks.json",checks)
        save("manifest.json",{name:sha(ROOT/name) for name in FILES})
    else:
        assert read(ROOT/"checks.json")==checks
        assert read(ROOT/"manifest.json")=={name:sha(ROOT/name) for name in FILES}
    print("verified",checks,"manifest",sha(ROOT/"manifest.json"))

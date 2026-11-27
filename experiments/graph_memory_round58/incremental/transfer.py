"""Transfer both frozen schedules without reusing any of the original nine repositories."""
import argparse
from collections import Counter
from measure_incremental import evaluate, HERE, panels, load, save


def run(modes=None, factory=None):
    r57=HERE.parents[1]/"graph_memory_round57"
    old = {repo.split("/")[-1].lower() for values in panels().values() for repo in values}
    traces, summaries = [], {}
    used = set()
    keys = []
    arms = []
    for source in ("seed_pair","replication"):
        inputs = load(r57/source/"events.json.gz")
        names = {name.split("/")[-1].lower() for name in inputs}
        assert len(names)==6 and not (names & (old|used))
        used |= names
        params = {} if modes is None else {"modes": modes,"factory":factory}
        trace, summary = evaluate({panel:inputs for panel in ("B","long")}, **params)
        arms = list(summary["B"])
        keys.extend(f"{source}/{schedule}/{repo}" for schedule in ("B","long") for repo in inputs)
        for row in trace:
            row["source"]=source
        traces += trace
        summaries[source] = summary
    per_repo = {key: Counter(dict.fromkeys(["queries",*arms],0)) for key in keys}
    for row in traces:
        key = "/".join((row["source"], row["panel"], row["repo"]))
        totals = per_repo.setdefault(key,Counter())
        totals["queries"] += 1
        for arm, meter in row["modes"].items():
            totals[arm] += meter.get("posting",0) + meter.get("body",0)
    return traces, dict(panels=summaries,projects=per_repo)


if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    traces, results=run()
    for name,obj in (("transfer-queries.json.gz",traces),("transfer-results.json",results)):
        if args.verify:
            assert obj==load(HERE/name)
        else:
            save(HERE/name,obj)
    for src,panels in results["panels"].items():
        for schedule,meters in panels.items():
            print(src,schedule,[(m,meters["1024/"+m]["bytes"]) for m in ("all","bound8","bound16")])

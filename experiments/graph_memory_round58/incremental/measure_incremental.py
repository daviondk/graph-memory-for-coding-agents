"""Replay identical durable SQLite streams for every fixed-budget incremental cache."""
import argparse
from collections import Counter
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from cache import ExactCache, MODES, cut, HERE
from wire import ranking
from bench import load, save, panels, prepare
from block_store import BlockStore


def evaluate(inputs=None, modes=MODES, factory=ExactCache):
    if inputs is None:
        inputs = panels()
    raw = []
    summary = {}
    with TemporaryDirectory(dir=HERE) as temp:
        for panel in ("B", "long"):
            for repo, history in sorted(inputs[panel].items()):
                ops, _ = prepare(history,panel)
                arms = {(b,m): factory(m,b) for b in (1024,4096) for m in modes}
                full = {}
                file = Path(temp)/(panel+"-"+repo.replace("/","_")+".sqlite")
                with closing(BlockStore(file,"filelist",True)) as store:
                    for op in ops:
                        if op[0] == "w":
                            _, j, rev, ids = op
                            assert store.append(j,rev,ids)
                            for f in ids:
                                full.setdefault(f,Counter()).update(i for i in ids if i != f)
                            continue
                        _, f, tie, _, oracle = op
                        scores = full.get(f,{})
                        threshold = sorted(scores.values(),reverse=True)[7] if len(scores)>=8 else 1
                        expected = {i:v for i,v in scores.items() if v>=threshold}
                        row = dict(panel=panel, repo=repo, prefix=store.next_id, anchor=f, modes={})
                        for (b,m), cache in arms.items():
                            frontier, meters = cache.read(store,f)
                            assert frontier == expected and ranking(frontier,f,tie,8) == oracle
                            row["modes"][f"{b}/{m}"] = meters
                        raw.append(row)
        for panel in ("long","B"):
            rows = [r for r in raw if r["panel"]==panel]
            summary[panel] = {}
            for name in rows[0]["modes"]:
                meters = [r["modes"][name] for r in rows]
                total = sum((Counter(m) for m in meters),Counter())
                del total["resident"]
                total.update(queries=len(rows), max_project_resident=max(m["resident"] for m in meters))
                total["bytes"] = total["body"] + total["posting"]
                summary[panel][name] = dict(total)
    return raw, summary


if __name__ == "__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    raw, measures = evaluate()
    for name, obj in (("queries.json.gz",raw),("results.json",measures)):
        if args.verify:
            assert obj==load(HERE/name)
        else:
            save(HERE/name,obj)
    for panel,summary in measures.items():
        print(panel, {name:v["bytes"] for name,v in summary.items()})

"""Exercise framed requests on the real SQLite archive and validate every returned rank."""
import argparse
from collections import Counter
from contextlib import closing
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from statistics import mean, median
import sys
from tempfile import TemporaryDirectory

from wire import METHODS, parse, receive, request, serve

HERE = Path(__file__).resolve().parent
R57 = HERE.parents[1] / "graph_memory_round57"
sys.path.insert(0, str(R57 / "block_index"))
from bench import load, save, prepare, panels
from block_store import BlockStore, unpack


def read_db(store, anchor, meter):
    row = store.db.execute("SELECT js FROM posting WHERE f=?", (anchor,)).fetchone()
    meter["queries"] += 1
    if row is None:
        return {}
    pointer = row[0]
    meter["posting_bytes"] += len(pointer)
    bodies, calls = store._fetch_events(unpack(pointer))
    meter["queries"] += calls
    counts = Counter()
    for (blob,) in bodies:
        meter["body_bytes"] += len(blob)
        counts.update(unpack(blob))
    counts.pop(anchor, None)
    return counts


def trial(ops, file, repo, panel):
    trace, examples = [], []
    with closing(BlockStore(file, "filelist", True)) as store:
        independent = []
        for op in ops:
            if op[0] == "w":
                _, event, revision, paths = op
                assert store.append(event, revision, paths)
                independent.append(set(paths))
                continue
            _, anchor, tie, _, expected = op
            assert set(tie) == set(range(len(tie)))
            counts = Counter(i for e in independent if anchor in e for i in e if i != anchor)
            assert min(tie.values(), default=0) >= 0
            row = dict(repo=repo, panel=panel, anchor=anchor, prefix=len(independent),
                       catalog=len(tie), positive=len(counts), methods={})
            for label, order in (("recent", tie), ("reverse", {i:i for i in tie})):
                gold = sorted(((i,counts[i]) for i in order if i != anchor),
                              key=lambda p: (-p[1], -order[p[0]], p[0]))[:8]
                if label == "recent":
                    assert gold == expected
                wire = {}
                for method in METHODS:
                    meter = Counter(queries=0, posting_bytes=0, body_bytes=0)
                    req = request(method, anchor, order)
                    rep = serve(req, lambda path: read_db(store, path, meter),
                                order if method == "shared" else None)
                    assert receive(rep, anchor, order) == gold
                    wire[method] = [len(req), len(rep)]
                    if "sql" in row:
                        assert row["sql"] == meter
                    else:
                        row["sql"] = dict(meter)
                row["methods"][label] = wire
                row[label+"_gold"] = gold
            if row["positive"]:
                recent = row["methods"]["recent"]
                examples.append((sum(recent["counts"])-sum(recent["frontier"]),
                                 dict(repo=repo, panel=panel, anchor=anchor, prefix=len(independent),
                                      catalog=len(tie), recent={i:s for i,s in tie.items() if s},
                                      scores=dict(counts), wire=recent)))
            trace.append(row)
    if examples:
        examples.sort(key=lambda x:x[0])
        examples = [examples[0][1],examples[len(examples)//2][1],examples[-1][1]]
    return trace, examples


def aggregate(trace):
    result = {}
    for panel in sorted({row["panel"] for row in trace}):
        rows = [r for r in trace if r["panel"] == panel]
        measures = dict(n=len(rows),repos=len({r["repo"] for r in rows}),
                        sql=dict(sum((Counter(r["sql"]) for r in rows),Counter())))
        for order in ("recent","reverse"):
            methods = {}
            for method in METHODS:
                exchange = [r["methods"][order][method] for r in rows]
                total = sorted(map(sum, exchange))
                methods[method] = dict(request=sum(p[0] for p in exchange),
                                       response=sum(p[1] for p in exchange),
                                       total=sum(total),mean=mean(total),median=median(total),
                                       p95=total[ceil(.95*len(total))-1], rpcs=len(rows))
            measures[order] = methods
        result[panel] = measures
    return result


def run():
    histories = panels()
    trace, examples, inputs = [], [], {}
    with TemporaryDirectory(dir=HERE) as scratch:
        for panel in ("B","long"):
            for name, rows in sorted(histories[panel].items()):
                ops, signature = prepare(rows,panel)
                inputs[panel+"/"+name] = signature
                part, sample = trial(ops,Path(scratch)/(name.replace("/","_")+".db"),name,panel)
                trace += part
                examples += sample
    assert inputs == load(R57.parent/"graph_memory_round56/durable/runs.json.gz")["oracle"]
    return {"trace":trace,"oracle":inputs}, aggregate(trace), examples


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    raw, metrics, examples = run()
    for name, obj in (("queries.json.gz",raw),("results.json",metrics),("examples.json.gz",examples)):
        if args.verify:
            assert obj == load(HERE/name) or json.loads(json.dumps(obj)) == load(HERE/name), name
        else:
            save(HERE/name,obj)
    print(json.dumps({p:{m:v["total"] for m,v in s["recent"].items()} for p,s in metrics.items()}))

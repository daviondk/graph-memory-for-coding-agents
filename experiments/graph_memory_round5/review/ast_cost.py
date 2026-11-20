"""Isolated local CPU microbenchmark of verifying a known lexical edge; excludes retrieval and model inference."""
import datetime
import itertools
import json
import platform
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from audit_reader import HERE, SOURCE, digest, load_inputs
from audit_ast import PARSER, classify_line, declaration_name


def verify(left,right,event):
    name,kind=declaration_name(left,event["root"])
    tree=PARSER.parse(right.encode())
    role=classify_line(tree,right,event["line"],name)["strong"] if name is not None else False
    return bool(role and kind=="type")


def summary(values):
    return {"median_ms":statistics.median(values),"mean_ms":statistics.mean(values),"p95_ms":float(np.quantile(values,.95))}

def main():
    packets={panel:load_inputs(panel) for panel in ("A","B")}
    tasks={}
    grouped=defaultdict(list)
    for s, rows in packets.items():
        for row in rows:
            if row["edge_event"] is not None:
                grouped[row["file"]].append((s,row))
    for file,rows in grouped.items():
        required={r["local_index"] for _,r in rows};data={};offset=0
        for batch in pq.ParquetFile(SOURCE/"archive_inputs"/file).iter_batches(columns=["context"],batch_size=64):
            for i in required:
                if offset <= i < offset+len(batch):
                    data[i]=batch.column(0)[i-offset].as_py()
            offset+=len(batch)
        for s,r in rows:
            texts=data[r["local_index"]]; e=r["edge_event"]
            tasks[s,r["id"]]=(texts[r["rank"][0]],texts[e["source"]],e)
    expected=json.loads((HERE/"ast_roles.json").read_text(encoding="utf8"))["records"]
    order=list(tasks)
    rng=random.Random(20261118)
    samples=defaultdict(list)
    for repeat in range(6):
        rng.shuffle(order)
        for s,k in order:
            start=time.perf_counter_ns()
            decision=verify(*tasks[s,k])
            elapsed=(time.perf_counter_ns()-start)/1e6
            assert decision==expected[s][k]["strong"]
            if repeat:
                samples[s,k].append(elapsed)
    out={}
    for s, pp in packets.items():
        per_item=[statistics.median(v) for (panel,k),v in samples.items() if s==panel]
        out[s]={"n_edges":len(per_item),"n_tasks":len(pp),"per_edge":summary(per_item),
                "mean_ms_per_all_tasks_counting_nonedge_as_zero":sum(per_item)/len(pp)}
    out.update({"cpu":platform.processor(),"python":platform.python_version(),"platform":platform.platform(),"clock":"perf_counter_ns",
                "repeats":5,"warmup":1,"shuffle":20261118,"script_sha":digest(Path(__file__)),"utc":datetime.datetime.now(datetime.UTC).isoformat()})
    (HERE/"ast_cost.json").write_text(json.dumps(out,indent=1),encoding="utf8")
    print(out)
if __name__=="__main__":main()

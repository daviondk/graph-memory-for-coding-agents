"""Score only sealed model decisions, using exactly the short control's public text scoring and pairing."""
import argparse
import gzip
import json
import re
from itertools import combinations
from pathlib import Path

from infer import D, read, save, sha
from score import first, sim, paired

B = D.parent / "java_reader"
METHODS = ("empty", "graph", "semlith", "oracle")
FIELDS = ("em", "es", "id_f1", "prompt_tokens")
IDENTIFIERS = re.compile(r"[A-Za-z_$][\w$]*")

def base_read(name):
    raw = (B / name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)

def compare(rows, left, right):
    return {name: paired(rows, left, right, name) for name in FIELDS}

def id_f1(candidate, target):
    a, b = set(IDENTIFIERS.findall(candidate)), set(IDENTIFIERS.findall(target))
    return 2 * len(a & b) / (len(a) + len(b)) if a or b else 1.0

def local():
    # The immutable call log seals replies before the target line is read.
    decision = read("long_decisions.json")
    packets = {p["id"]: p for p in read("long_packets.json.gz")}
    arms = read("long_assignment.json")
    base = {p["id"]: p for p in base_read("B_packets.json.gz")}
    rows = read("long_items.json.gz")
    assert len(rows) == len(arms) == len(packets) == 96
    distinct = set(k for v in arms.values() for k in v.values())
    assert set(decision) == {x + ".json.gz" for x in distinct}
    reuse = read("long_reuse.json")
    assert len(distinct) == reuse["total_unique"]
    for p in packets.values():
        b = base[p["id"]]
        assert all(p["ranks"][a] == b["ranks"][a] and p["snippets"][a] == b["snippets"][a] for a in ("graph","semlith"))
    assert all(len(x["methods"]) == 4 for x in rows)
    # Diagnostic: is the exact target independently present among the supplied oracle lines?
    oracle_copy = [r["gold"] in {line.strip() for line in packets[r["id"]]["snippets"]["oracle"][0].splitlines()} for r in rows]
    r = read("long_results.json")
    method_values = r["all"]["methods"]
    report = {
        "n": len(rows), "repositories": len({x["repo"] for x in rows}), "main": method_values,
        "comparisons": {a+"-"+b: compare(rows,a,b) for a,b in combinations(METHODS,2)},
        "logical_generations": sum(len(v) for v in arms.values()), "distinct_requests": len(distinct),
        "prior_identical_request_reuse": len(reuse["reused"]), "new_unique": len(distinct)-len(reuse["reused"]),
        "prompt_tokens_distinct": r["prompt_tokens"], "completion_tokens_distinct": r["generated_tokens"],
        "different_graph_semlith": sum(x["different"] for x in rows),
        "different_prefix_count": sum(p["ctx"] != base[p["id"]]["ctx"] for p in packets.values()),
        "prefix_token_mean_long": sum(p["ctx_tokens"] for p in packets.values())/len(rows),
        "prefix_token_mean_short": sum(p["short_ctx_tokens"] for p in packets.values())/len(rows),
        "range_long_prefix_tokens": [min(p["ctx_tokens"] for p in packets.values()),max(p["ctx_tokens"] for p in packets.values())],
        "range_short_prefix_tokens": [min(p["short_ctx_tokens"] for p in packets.values()),max(p["short_ctx_tokens"] for p in packets.values())],
        "upper_1024_count": sum(p["ctx_tokens"] == 1024 for p in packets.values()),
        "oracle_contains_exact_target_line": sum(oracle_copy),
        "oracle_em_if_present": sum(x["methods"]["oracle"]["em"] for x,yes in zip(rows,oracle_copy) if yes),
        "oracle_em_if_absent": sum(x["methods"]["oracle"]["em"] for x,yes in zip(rows,oracle_copy) if not yes),
        "data_sha256": {n:sha((D/n).read_bytes()) for n in ["long_items.json.gz","long_results.json","long_decisions.json","long_input_lock.json"]},
    }
    save("long_extended.json", report)
    return rows

def mixed(rows, include_empty):
    artifact="B_items.json.gz"
    short={r["id"]:r for r in base_read(artifact)}
    if include_empty:
        zassign=base_read("Z_assignment.json")
        sealed=base_read("Z_decisions.json")
    for row in rows:
        ident=row["id"]
        b=short[ident]
        assert row["repo"]==b["repo"] and row["gold"]==b["gold"]
        for a in ("graph","semlith"):
            row["methods"]["short_"+a]=b["methods"][a]
        if include_empty:
            k=zassign[ident]["empty"]
            name="Z_calls/"+k+".json.gz"
            assert sha((B/name).read_bytes())==sealed[k+".json.gz"]
            o=base_read(name)["reply"]
            answer=first(o["choices"][0]["message"].get("content") or "")
            row["methods"]["short_empty"]=dict(em=int(answer==row["gold"]),es=sim(answer,row["gold"]),
                id_f1=id_f1(answer,row["gold"]),prompt_tokens=o["usage"]["prompt_tokens"])
    methods=("graph","semlith","empty") if include_empty else ("graph","semlith")
    d={a:compare(rows,a,"short_"+a) for a in methods}
    summarised={a:{f:sum(row["methods"]["short_"+a][f] for row in rows)/(1 if f=="em" else len(rows)) for f in FIELDS} for a in methods}
    src=[artifact,"B_decisions.json"]+(["Z_assignment.json","Z_decisions.json"] if include_empty else [])
    save("short_long_compare.json",dict(n=len(rows),short=summarised,long_minus_short=d,sources={s:sha((B/s).read_bytes()) for s in src}))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--short", action="store_true")
    parser.add_argument("--include-empty", action="store_true")
    args=parser.parse_args()
    rows=local()
    if args.short:
        mixed(rows,args.include_empty)
if __name__=="__main__":
    main()

"""Export public identities, strong ranks and observed parent states without reading judgments."""
from common import *

def main():
    assert sha(HERE / "PROTOCOL_RU.md") == PLAN
    first = EXPERIMENTS / "graph_memory_round47/facet_reader"
    conf = EXPERIMENTS / "graph_memory_round47/facet_confirmation"
    paths = dict(items=UPSTREAM / "data/cal500/items.jsonl.gz",
                 panels=first / "panels.json", first=first / "predictions.json.gz",
                 conf=conf / "predictions.json.gz", costs=EXPERIMENTS / "graph_memory_round34/external_transfer/features.json.gz",
                 lineage=EXPERIMENTS / "graph_memory_round50/cache_replication/cal-lineage.json.gz")
    inputs = {k:read(v) for k,v in paths.items() if k != "items"}
    panels = {k: inputs["panels"][k] for k in ("dev", "outside")}
    selected = set(panels["dev"] + panels["outside"])
    with gzip.open(paths["items"], "rt", encoding="utf8") as handle:
        raw = {s["state_id"]: s for s in map(json.loads, handle) if s["state_id"] in selected}
    assert len(raw) == len(selected) == 305
    result = {}
    for panel, questions in panels.items():
        for q in questions:
            state = raw[q]
            z = inputs["conf" if panel == "dev" else "first"][q]
            order = z["rank"]["union_mask" if panel == "dev" else "qwen_union_mask"]
            assert sorted(order) == list(range(len(z["ids"]))) and z["repo"] == state["repo"]
            raw_candidates = {r["evidence_id"]:r for r in state["candidate_evidence"]}
            assert set(z["ids"]) == set(raw_candidates)
            costs = inputs["costs"][q]
            token = dict(zip(costs["ids"], costs["qw"], strict=True))
            keys = []
            for identifier in z["ids"]:
                r = raw_candidates[identifier]
                keys.append(key([state["repo"], state["base_commit"], r.get("source_type"), r.get("source_path"),
                                 r.get("line_start"), r.get("line_end"), r.get("content_sha256"), r.get("content_excerpt")]))
            history = inputs["lineage"][q]["true"]
            assert set(history).issubset(questions)
            for p in history:
                previous = raw[p]
                assert previous["repo"] == state["repo"] and previous["instance_id"] == state["instance_id"]
                assert previous["base_commit"] == state["base_commit"]
                # Use authoritative raw events in addition to the archived run-specific lineage.
                a = previous["trajectory_prefix"]
                b = state["trajectory_prefix"]
                assert len(a) < len(b) and a == b[:len(a)]
            seen = z["seen"]
            assert [seen[i] for i in order] == sorted(seen)
            result[q] = dict(panel=panel, repo=z["repo"], ids=z["ids"], keys=keys, tokens=[token[i] for i in z["ids"]],
                             current=order, seen=seen, parent=history[-1] if history else None, depth=len(history))
    repos = [{result[q]["repo"] for q in questions} for questions in panels.values()]
    assert not repos[0] & repos[1]
    keyed = {}
    for row in result.values():
        for ident, n in zip(row["keys"],row["tokens"]):
            assert n > 0 and keyed.setdefault(ident,n)==n
    save("inputs.json.gz", result)
    save("input-seal.json", dict(protocol=PLAN, inputs=sha(HERE/"inputs.json.gz"),
         code={f:sha(HERE/f) for f in ("common.py","prepare.py")}, sources={k:sha(v) for k,v in paths.items()}))
    print("Prepared",len(result),"states,",len(keyed),"immutable units,",sum(bool(v["parent"]) for v in result.values()),"strict transitions.")
if __name__ == "__main__":
    main()


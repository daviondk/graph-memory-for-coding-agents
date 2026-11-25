"""Warm single-query CPU graph execution conditional on a sealed gate decision."""
import hashlib
import sqlite3
import statistics
import sys
import time
from pathlib import Path

import gate

ROOT = Path(__file__).resolve().parent
GRAPH = ROOT.parent / "residual_graph"
sys.path.insert(0, str(GRAPH / "cpu_fallback"))
sys.path.insert(1, str(GRAPH))

import numpy as np
import torch
from fallback import data
from fit_graph import features, model_cfg, build_model_from_config, tensorize_provenance_ranking_task
from forecasts import Lookup
from setup_graph import RUN
from graph_memory.models.graph_retriever.batching import collate_evidence_tasks, split_batch_node_scores
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint


def sampling_key(q):
    return hashlib.sha256(("R20 gate runtime v1|" + q).encode()).digest()


def measure(panel):
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    start = time.perf_counter()
    base = GRAPH / "cpu_fallback" / panel
    sealed = gate.load(base / "forecast-seal.json")["files"]
    weights = base / "best.pt"
    assert gate.sha(weights) == gate.load(base / "checkpoint.json")["sha"]
    policy = gate.load(ROOT / f"{panel}-model.json")
    decpath = ROOT / f"{panel}-decisions.json.gz"
    assert gate.sha(decpath) == gate.load(ROOT / f"{panel}-decision-seal.json")["decisions"]
    decisions = {row["q"]:row["call"]["gate50"] for row in gate.load(decpath)}
    feats = {row["q"]:row for row in gate.load(ROOT / "test-features.json.gz")}
    ids = sorted(decisions, key=sampling_key)[:96]
    sources = {feats[q]["t"] for q in ids}
    lookup = Lookup(sqlite3.connect((RUN / "vectors.sqlite3").resolve().as_uri()+"?mode=ro", uri=True), "ft")
    model = build_model_from_config(model_cfg).eval()
    model.load_state_dict(load_rgcn_checkpoint(weights, map_location="cpu").payload["model_state_dict"])
    tasks = {}
    for _, reqs, labels in data("test", sources):
        assert not labels
        rs = [r for r in reqs if r.task_id in ids]
        if not rs:
            continue
        mem = np.empty((len(rs)*(len(rs[0].graph.nodes)+1), 768), dtype="<f4")
        prov, used = features(rs, lookup, mem, 0)
        assert used == len(mem)
        for r in rs:
            tasks[r.task_id] = tensorize_provenance_ranking_task(r, model_config=model_cfg,
                                      text_embedding_provider=prov, seed_signal_provider=prov)
    assert set(tasks) == set(ids)
    official = {}
    for p in sorted(base.glob("forecasts-rgcn-*.json.gz")):
        assert gate.sha(p) == sealed[p.name]
        for r in gate.load(p):
            if r["q"] in tasks:
                official[r["q"]] = {n["node_id"]:n["score"] for n in r["rr"]}
    assert set(official) == set(tasks)
    prep_elapsed = time.perf_counter() - start
    checks = {}
    largest_gap = 0.
    prefix_agreement = 0
    warm_start = time.perf_counter()
    with torch.inference_mode():
        for q in ids:
            batch = collate_evidence_tasks([tasks[q]])
            scores = model(batch)
            data_by_id = dict(split_batch_node_scores(batch,scores)[q])
            assert set(data_by_id) == set(official[q])
            largest_gap = max(largest_gap, max(abs(official[q][k]-s) for k,s in data_by_id.items()))
            order = lambda vals: sorted(vals,key=lambda k:(-vals[k],k))[:10]
            prefix_agreement += order(data_by_id) == order(official[q])
            checks[q] = float(scores.sum().item())
        warm_elapsed = time.perf_counter() - warm_start
        pairs = []
        for arms in (("always","gate"),("gate","always"),("gate","always"),("always","gate")):
            entry = {"order":arms}
            for arm in arms:
                elapsed = time.perf_counter()
                calls = 0
                checksum = 0.
                for q in ids:
                    run = True
                    if arm == "gate":
                        s = gate.raw_score(feats[q],policy,"gate")
                        run = gate.call(s,q,"gate",policy["cutoffs"]["gate"]["50"])
                        assert run == decisions[q]
                    if run:
                        calls += 1
                        batch = collate_evidence_tasks([tasks[q]])
                        checksum += float(model(batch).sum().item())
                seconds = time.perf_counter() - elapsed
                selected = ids if arm=="always" else [q for q in ids if decisions[q]]
                assert calls == len(selected) and abs(checksum-sum(checks[q] for q in selected)) <= 1e-5
                entry[arm] = {"seconds":seconds,"calls":calls,"checksum":checksum}
            entry["ratio_gate_to_always"] = entry["gate"]["seconds"]/entry["always"]["seconds"]
            pairs.append(entry)
    report = dict(n=len(ids),q=ids,trajectories=len(sources),decision_sha=gate.sha(decpath),
                  features_sha=gate.sha(ROOT/"test-features.json.gz"),checkpoint_sha=gate.sha(weights),
                  code_sha=gate.sha(Path(__file__)),protocol_sha=gate.sha(ROOT/"RUNTIME_RU.md"),
                  cpu_threads=torch.get_num_threads(),torch_version=str(torch.__version__),test_labels_read=False,
                  argmax10_order_matches=prefix_agreement,largest_score_gap=largest_gap,prepare_s=prep_elapsed,
                  warm_s=warm_elapsed,pairs=pairs,median_ratio=statistics.median(p["ratio_gate_to_always"] for p in pairs))
    gate.put(ROOT/f"{panel}-runtime.json",report)
    print(panel, f"{len(ids)} queries, {pairs[0]['gate']['calls']} calls, median fraction {report['median_ratio']:.3f},"
          f" score delta {largest_gap:.3g}, top10 match {prefix_agreement}", flush=True)


if __name__ == "__main__":
    measure(sys.argv[1])

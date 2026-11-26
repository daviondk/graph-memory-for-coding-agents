"""CPU native inference on physically rebuilt prefix graphs. No gold readers."""
import os
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "RAYON_NUM_THREADS"):
    os.environ[name] = "2"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import argparse
from collections import Counter, defaultdict
import sys
from time import monotonic
from shared import D, W, C, OFF, SEEDS, ARMS, sha, read, save, panel, pack
sys.path.insert(0, str(OFF))
import official as api
import numpy as np
from graph_memory.trajectories import CanonicalTrajectory, SourceIntent
from graph_memory.graphs.provenance import build_provenance_graph
from graph_memory.datasets.isetrace.adapter import adapt_isetrace_record, parse_isetrace_record


def indexes(sh):
    state = C / f"state-{sh}.json.gz"
    assert sha(state) == read(C / f"state-{sh}-seal.json")["data"]
    records = api.TR / f"forecasts-main-{sh}.json.gz"
    assert sha(records) == read(api.TR / "forecast-seal.json")["forecasts"][records.name]
    ids = {r["q"]: [n["node_id"] for n in r["rr"]] for r in read(records)}
    costs = {r["q"]: [n["token_count"] for n in r["rr"]] for r in read(records)}
    expected = {(q, cut): (t, step, avail) for q, t, cut, step, avail, *_ in read(state) if cut in (50, 100)}
    return ids, costs, expected


def native_inputs(seed):
    db, _ = api.connect(seed)
    for _, name, _ in db.execute("pragma database_list").fetchall():
        if name != "temp" and name.isidentifier():
            db.execute(f"pragma {name}.mmap_size=3000000000")
    pub, private = api.seed_paths(seed)
    models = {}
    for arm in ARMS:
        fit = read(pub / arm / "fit.json")
        ck = private / fit["attempt"] / "best.pt"
        prior = read(pub / arm / "forecast-seal.json")
        assert sha(ck) == fit["checkpoint"] == prior["checkpoint"]
        assert fit["weight"] == prior["ft"] == read(pub / "embeddings.json")["weight"]
        stored = api.inf.load_rgcn_checkpoint(ck, map_location="cpu")
        cfg = stored.model_config
        assert cfg.ablation_name == arm and cfg.encoder_dim == 768
        model = api.fit.build_model_from_config(cfg)
        model.load_state_dict(stored.payload["model_state_dict"])
        models[arm] = (cfg, model.to("cpu").eval())
    return db, RepeatedLookup(api.fit.Lookup(db, "ft")), models


class RepeatedLookup:
    """Bound the in-memory cache; each distinct string still uses the signed native FP32 cache."""
    def __init__(self, native):
        self.native = native
        self.rows = {}

    def encode(self, texts, **options):
        if len(self.rows) > 12000:
            self.rows.clear()
        missing = list(dict.fromkeys(text for text in texts if text not in self.rows))
        if missing:
            values = self.native.encode(missing, **options)
            self.rows.update((text, value) for text, value in zip(missing, values, strict=True))
        return np.stack([self.rows[text] for text in texts])


def prefix_graph(tr, step, chunker):
    events = tr.events[:step + 1]
    prefix = CanonicalTrajectory(
        trajectory_id=tr.trajectory_id, source_dataset=tr.source_dataset,
        source_revision=tr.source_revision, source_record_id=tr.source_record_id,
        intents=(SourceIntent(intent_id="as-of", text="as-of"),), tool_definitions=(),
        events=events, final_response="", source_metadata=None,
        source_total_steps=sum(e.event_type == "tool_call" for e in events))
    graph = build_provenance_graph(prefix, content_chunker=chunker)
    allowed = {e.event_id for e in events}
    assert all(s.event_id in allowed for n in graph.nodes for s in n.source_spans)
    assert all(s.event_id in allowed for e in graph.edges for s in e.source_spans)
    return graph


def midstep(tr):
    ends = []
    active = 0
    for j, e in enumerate(tr.events):
        if e.event_type == "tool_call":
            active += 1
        elif e.event_type == "tool_output":
            active -= 1
            assert active >= 0
            if active == 0:
                ends.append(j)
    assert not active and ends
    return ends[(len(ends) - 1) // 2], ends[-1]


def score_graph(graph, questions, models, profiler):
    pool = tuple(api.pilot.native.provenance_unit_candidates(graph))
    requests = [api.ExecutionProvenanceRankingRequest(task_id=q, query_text=txt, candidates=pool, graph=graph)
                for q, txt in questions.items()]
    by_q = {q: {} for q in questions}
    for seed, (_, lookup, nets) in models.items():
        start = monotonic()
        cells = (len(graph.nodes) + 1) * len(questions)
        provider, used = api.fit.features(requests, lookup, np.empty((cells, 768), dtype=np.float32), 0)
        assert cells == used
        profiler["cached_vectors_seconds"] += monotonic() - start
        for arm, (cfg, net) in nets.items():
            start = monotonic()
            tasks = [api.fit.tensorize_provenance_ranking_task(req, model_config=cfg,
                     text_embedding_provider=provider, seed_signal_provider=provider) for req in requests]
            profiler["tensorize_seconds"] += monotonic() - start
            for batch in api.inf.build_evidence_dataloader(tasks, per_device_graph_batch_size=128, shuffle=False, random_seed=seed):
                start = monotonic()
                assert batch.sample_node_features.device.type == "cpu"
                with api.torch.inference_mode():
                    values = net(batch)
                assert api.torch.isfinite(values).all()
                ranked = api.old.orders(batch, values)
                profiler["forward_rank_seconds"] += monotonic() - start
                for q, order in ranked.items():
                    assert len(order) == len(pool) and set(order) == {c.item_id for c in pool}
                    by_q[q][f"{seed}/{arm}"] = order
    return by_q


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--shards", type=int, nargs="+", default=list(range(8)))
    args = parser.parse_args()
    api.torch.set_num_threads(2)
    api.torch.set_num_interop_threads(1)
    assert not api.torch.cuda.is_available()
    plan = read(D / "registration.json")
    assert plan["protocol"] == sha(D / "PROTOCOL_RU.md") and plan["split"] == sha(OFF / "split.json.gz")
    split = read(OFF / "split.json.gz")["test"]
    named = defaultdict(list)
    for r in split:
        named[r["t"]].append(r["q"])
    selected = set(plan["terminal_panel"])
    quick = set(plan["terminal_panel"][:3])
    assert plan["terminal_panel"] == panel(named)
    wanted = {v["q"] for v in split}
    qtext = {r["id"]: r["query"] for _, r in api.pilot.stream(api.pilot.Q) if r["id"] in wanted}
    assert len(qtext) == 2000
    locks = {v["path"]: v["sha256"] for v in read(api.R18 / "isetrace_official/source-lock.json")}
    tokenizer = api.pilot.offsets(api.pilot.Tokenizer.from_file(str(api.pilot.CACHE / "tokenizer.json")))
    def chunk(txt):
        return api.pilot.token_chunks(txt, tokenizer=tokenizer, max_tokens=504, overlap_tokens=64)
    models = {s: native_inputs(s) for s in SEEDS}
    label = "quick" if args.quick else "forecast"
    for sh in args.shards:
        start = monotonic()
        dest = D / f"{label}-{sh}.json.gz"
        seal = D / f"{label}-{sh}-seal.json"
        if seal.exists():
            prev = read(seal)
            assert sha(dest) == prev["data"] and sha(D / "registration.json") == prev["registration"]
            continue
        ids, costs, expected = indexes(sh)
        mapping = {q: {name: i for i, name in enumerate(entries)} for q, entries in ids.items()}
        source = api.RAW / f"trajectories-{sh:05d}.jsonl"
        assert sha(source) == locks["trajectories/" + source.name]
        rows = []
        traces = []
        profiler = Counter()
        for _, raw in api.pilot.stream(source):
            t = raw["session_id"]
            if t not in named or (args.quick and t not in quick):
                continue
            tr = adapt_isetrace_record(parse_isetrace_record(raw), source_revision=api.pilot.RAW[1])
            middle, last = midstep(tr)
            for pct, step in [(50, middle)] + ([(100, last)] if t in selected else []):
                start_graph = monotonic()
                graph = prefix_graph(tr, step, chunk)
                profiler["build_graph_seconds"] += monotonic() - start_graph
                qs = {q: qtext[q] for q in named[t]}
                scores = score_graph(graph, qs, models, profiler)
                traces.append([t, pct, step, len(graph.nodes), len(graph.edges), graph.fingerprint()])
                for q, ranked in scores.items():
                    assert expected[q, pct][:2] == (t, step)
                    available = set(expected[q, pct][2])
                    out = {}
                    for k, order in ranked.items():
                        # Only the emitted native result is translated into the external scoring vocabulary.
                        seq = [mapping[q][n] for n in order]
                        assert len(seq) == len(available) and set(seq) == available
                        out[k] = seq
                    rows.append([q, t, pct, out])
            if len(traces) % 25 == 0:
                print("shard", sh, "graphs", len(traces), "seconds", round(monotonic() - start, 1), flush=True)
        assert len({(r[0], r[2]) for r in rows}) == len(rows)
        save(dest, rows)
        stats = dict(data=sha(dest), registration=sha(D / "registration.json"), code=sha(D / "native.py"),
                     source=sha(source), profiler=profiler, seconds=monotonic() - start,
                     records=len(rows), traces=traces)
        save(seal, stats)
        print(label, sh, len(rows), round(stats["seconds"], 2), flush=True)
    for conn, *_ in models.values():
        conn.close()


if __name__ == "__main__":
    main()

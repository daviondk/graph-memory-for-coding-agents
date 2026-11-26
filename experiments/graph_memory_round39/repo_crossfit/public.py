"""Construct inference features from the public export, independently of fitted SERBench models."""
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

for variable in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
SET_READER = ROOT.parent / "set_reader"
R34 = WORK / "graph_memory_round34/external_transfer"
sys.path.insert(0, str(SET_READER))
from data import UP, PUB, sha, norm, tokens, splitwords, rank, order, get, stream, native, sets_native, target


def write(name, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    (ROOT / name).write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)


def fold_by_repository(rows):
    repos = {row["repo"] for row in rows.values()}
    ordered = sorted(repos, key=lambda repo: hashlib.sha256(("r39-public-repos-01/" + repo).encode()).digest())
    return {repo: i % 5 for i, repo in enumerate(ordered)}


def extract(rows):
    vectors_path = UP / "dense_vectors.npy"
    assert sha(vectors_path) == get(UP / "dense_runtime.json")["vectors_sha256"]
    vectors = np.load(vectors_path, mmap_mode="r")
    layouts = {item["state_id"]: item for item in stream(UP / "dense_inputs.jsonl.gz") if item["state_id"] in rows}
    fields = ("issue", "information_need", "current_subgoal", "current_hypothesis", "current_observation",
              "latest_test_output", "search_queries", "opened_files", "current_diff")
    out = {}
    for item in stream(PUB / "items.jsonl.gz"):
        q = item["state_id"]
        if q not in rows:
            continue
        row = rows[q]
        index = {c["evidence_id"]: c for c in item["candidate_evidence"]}
        candidates = [index[k] for k in row["ids"]]
        layout = layouts[q]
        lookup = dict(layout["candidates"])
        matrix = vectors[[lookup[k] for k in row["ids"]]].astype(np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        query = vectors[layout["queries"]["state"]].astype(np.float32)
        cosine = matrix @ (query / np.linalg.norm(query))
        raw = np.array(row["x"]).T
        # Positions 3 and 4 are filled only after the current fold's union cost is fitted.
        columns = [np.log1p(row["ranks"][k]) for k in ("dense_state", "dense_addresses", "bm25")]
        n = len(candidates)
        columns += [np.zeros(n), np.zeros(n), cosine, cosine.max() - cosine, *raw[1:4], np.log1p(row["qw"])]
        paths = [norm(c["source_path"]) for c in candidates]
        words = [tokens(c["content_excerpt"]) for c in candidates]
        docs = [bag | splitwords(bag) for bag in words]
        path_words = [set(re.findall(r"[a-z0-9]{2,}", path)) for path in paths]
        test_path = np.array([bool(re.search(r"(^|[/_.-])tests?([/_.-]|$)", p)) for p in paths], float)
        observed = np.array([c["observed_by_state"] for c in candidates], float)
        columns += [observed, test_path, np.log1p([p.count("/") for p in paths]), np.log1p([len(s) for s in words])]
        counts = Counter(t for bag in docs for t in bag)
        idf = {t: math.log1p(n / (1 + cnt)) for t, cnt in counts.items()}
        for field in fields:
            field_value = item.get(field) or ""
            literal = (field_value if isinstance(field_value, str) else json.dumps(field_value, ensure_ascii=False)).lower()
            query_words = tokens(field_value)
            query_words |= splitwords(query_words)
            weighted = np.array([sum(idf[t] for t in sorted(bag & query_words)) for bag in docs])
            query_tests = bool(re.search(r"\b(test|tests|verify|failure|assertion)\b", literal))
            columns += [weighted / (1 + sum(idf.get(t, 0.) for t in sorted(query_words))), np.log1p(rank(weighted)),
                        [len(bag & query_words) / (1 + len(bag)) for bag in path_words],
                        [bool(p) and p in literal for p in paths],
                        [bool(p) and p.rsplit("/", 1)[-1] in literal for p in paths], test_path * query_tests]
        features = np.column_stack(columns).astype(np.float32)
        assert np.isfinite(features).all() and not np.any(features[:, 3:5])
        out[q] = features
    assert out.keys() == rows.keys()
    return out

"""Produce predictions from issue text and source snapshots before opening evaluation labels."""
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from cache_paths import CACHE

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(CACHE / "deps"), str(ROOT / "deps"), str(ROOT / "upstream")]
from explorers.bm25 import BM25Explorer
from rank_bm25 import BM25Okapi


def tokens(text):
    terms = []
    for atom in re.findall(r"[A-Za-z][A-Za-z0-9]*|[0-9]+", text):
        terms.append(atom.lower())
        pieces = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+", atom)
        if len(pieces) > 1:
            terms.extend(piece.lower() for piece in pieces)
    return terms


def add_votes(fused, scores, weight, eligible=None):
    order = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
    for rank, idx in enumerate(order, 1):
        if eligible is None or eligible[idx]:
            fused[idx] += weight / (60 + rank)


def process(task, force=False):
    iid = task["instance_id"]
    outpath = ROOT / "predictions" / (iid + ".json")
    outpath.parent.mkdir(exist_ok=True)
    if outpath.exists() and not force:
        return
    if not (ROOT / "receipts" / (iid + ".json")).is_file():
        raise FileNotFoundError(iid + " snapshot is incomplete")
    query = task["problem_statement"]
    started = time.perf_counter()
    official = BM25Explorer(CACHE / "snapshots" / iid)
    index_s = time.perf_counter() - started
    chunks = official._chunks
    baseline = official.explore(instance_id=iid, query=query, top_k=5)
    gold_blind_regions = [[v.path, v.start, v.end] for hit in baseline for v in hit.regions]
    start_fusion = time.perf_counter()
    qtokens = tokens(query)
    code_tokens = [tokens(c.content) for c in chunks]
    path_tokens = [tokens(c.path) for c in chunks]
    qset = set(qtokens)
    votes = [0.0] * len(chunks)
    add_votes(votes, official._bm25.get_scores(query.split()), 1)
    add_votes(votes, BM25Okapi(code_tokens).get_scores(qtokens), 2)
    add_votes(votes, BM25Okapi(path_tokens).get_scores(qtokens), 1, [bool(qset.intersection(t)) for t in path_tokens])
    chosen = sorted(range(len(chunks)), key=votes.__getitem__, reverse=True)[:5]
    candidate = [[chunks[i].path, chunks[i].start, chunks[i].end] for i in chosen]
    inventory = hashlib.sha256()
    for chunk in chunks:
        inventory.update(json.dumps([chunk.path, chunk.start, chunk.end, chunk.content], ensure_ascii=False).encode())
    row = {"instance_id": iid, "repo": task["repo"], "base_commit": task["base_commit"], "chunks": len(chunks),
           "chunk_inventory_sha256": inventory.hexdigest(), "upstream_index_seconds": index_s,
           "fusion_added_seconds": time.perf_counter() - start_fusion, "bm25": gold_blind_regions, "fusion": candidate}
    outpath.write_text(json.dumps(row, indent=2), encoding="utf8")
    print(iid, len(chunks), f"{time.perf_counter() - started:.2f}s", flush=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--ready", action="store_true", help="process available snapshots, useful while fetching others")
    p.add_argument("--force", action="store_true", help="recompute every prediction even when receipts exist")
    options = p.parse_args()
    for task in json.loads((ROOT / "tasks.json").read_text(encoding="utf8")):
        if options.ready and not (ROOT / "receipts" / (task["instance_id"] + ".json")).exists():
            continue
        process(task, force=options.force)

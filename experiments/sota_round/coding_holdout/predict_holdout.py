"""Rank the three declared systems, using only issues and their base snapshots."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODING = ROOT.parent / "coding"
sys.path.insert(0, str(CODING))
from cache_paths import CACHE
sys.path[:0] = [str(CACHE / "deps"), str(CODING / "deps"), str(CODING / "upstream")]
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.metrics.pairwise import cosine_similarity
from explorers.rag_tfidf import TFIDFExplorer
from rank_bm25 import BM25Okapi
from predict import add_votes, tokens

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*")
SOURCE = re.compile(r"\b(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)|(" + NAME.pattern + ")")


def shaped(name):
    return "_" in name or "." in name or any(c.isupper() for c in name[1:])


def collect(items, limit):
    names = {}
    for name in items:
        names[name.lower()] = None
        if len(names) == limit:
            break
    return " ".join(names)


def chunk_names(chunk):
    names = (match[1] or match[2] for match in SOURCE.finditer(chunk.content) if match[1] or shaped(match[2]))
    return chunk.path + " " + chunk.path + " " + collect(names, 128)


def prior_order(chunks, query):
    qtokens = tokens(query)
    qset = set(qtokens)
    votes = [0.0] * len(chunks)
    raw = BM25Okapi([c.content.split() for c in chunks])
    add_votes(votes, raw.get_scores(query.split()), 1)
    del raw
    normalized = BM25Okapi([tokens(c.content) for c in chunks])
    add_votes(votes, normalized.get_scores(qtokens), 2)
    del normalized
    paths = [tokens(c.path) for c in chunks]
    add_votes(votes, BM25Okapi(paths).get_scores(qtokens), 1, [bool(qset.intersection(p)) for p in paths])
    return sorted(range(len(chunks)), key=votes.__getitem__, reverse=True)


def merge(chunks, query_names, word_scores, word_order, previous):
    if not query_names:
        return word_order
    hv = HashingVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3, 4), n_features=2**17,
                           norm=None, alternate_sign=False, dtype=np.float32)
    transformer = TfidfTransformer(sublinear_tf=True)
    matrix = transformer.fit_transform(hv.transform(chunk_names(c) for c in chunks))
    char = cosine_similarity(transformer.transform(hv.transform([query_names])), matrix)[0]
    votes = [0.0] * len(chunks)
    for rank, i in enumerate(word_order, 1):
        if word_scores[i] > 0:
            votes[i] += 3 / (60 + rank)
    for rank, i in enumerate(previous, 1):
        votes[i] += 1 / (60 + rank)
    add_votes(votes, char, 2, char > 0)
    return sorted(range(len(chunks)), key=votes.__getitem__, reverse=True)


def infer(task):
    iid, query = task["instance_id"], task["problem_statement"]
    start = time.perf_counter()
    author = TFIDFExplorer(CACHE / "snapshots" / iid)
    chunks = author._chunks
    scores = cosine_similarity(author._vectorizer.transform([query]), author._chunk_matrix)[0]
    word_order = scores.argsort()[::-1]
    tf = [[r.path, r.start, r.end] for v in author.explore(instance_id=iid, query=query, top_k=5) for r in v.regions]
    word_time = time.perf_counter() - start
    previous = prior_order(chunks, query)
    prior_time = time.perf_counter() - start - word_time
    names = collect((m[0] for m in NAME.finditer(query) if shaped(m[0])), 24)
    new = merge(chunks, names, scores, word_order, previous)
    char_time = time.perf_counter() - start - word_time - prior_time
    def items(indices):
        return [[chunks[i].path, chunks[i].start, chunks[i].end] for i in indices[:5]]
    assert items(word_order) == tf and all(1 <= end-start+1 <= 80 for _, start, end in tf)
    inventory = hashlib.sha256()
    for c in chunks:
        inventory.update(json.dumps([c.path,c.start,c.end,c.content],ensure_ascii=False).encode())
    return {"instance_id": iid, "repo": task["repo"], "base_commit": task["base_commit"],
            "chunks":len(chunks), "chunk_inventory_sha256":inventory.hexdigest(), "query_names_count":len(names.split()),
            "tfidf_seconds":word_time,"prior_additional_seconds":prior_time,"char_additional_seconds":char_time,
            "tfidf":tf,"prior":items(previous),"new":items(new)}


def process(task):
    iid = task["instance_id"]
    output = ROOT / "predictions" / (iid+".json")
    if output.exists():
        return
    if not (ROOT / "receipts" / (iid+".json")).exists():
        raise RuntimeError("Missing completed source snapshot for " + iid)
    row = infer(task)
    output.write_text(json.dumps(row,indent=2),encoding="utf8")
    print(iid, "sealed", f"{row['tfidf_seconds']+row['prior_additional_seconds']+row['char_additional_seconds']:.2f}s",flush=True)


def seal():
    tasks = json.loads((ROOT / "tasks.json").read_bytes())
    lock = json.loads((ROOT / "design_lock.json").read_bytes())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha(ROOT / "protocol.md") == lock["protocol_sha256"] and sha(ROOT/"tasks.json") == lock["tasks_sha256"]
    digests = {}
    for t in tasks:
        q = t["instance_id"]
        path = ROOT / "predictions" / (q + ".json")
        row = json.loads(path.read_bytes())
        assert q == row["instance_id"] and all(len(row[arm])==5 for arm in ["tfidf","prior","new"])
        digests[q] = sha(path)
    result = {"prediction_hashes":digests, "prediction_code":sha(Path(__file__)), "protocol":lock["protocol_sha256"],
              "tasks":lock["tasks_sha256"],"joint_sha256":hashlib.sha256(json.dumps(digests,sort_keys=True).encode()).hexdigest()}
    (ROOT / "predictions_lock.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print("prediction lock",result["joint_sha256"],flush=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--workers",type=int,default=3)
    p.add_argument("--check-pilot",action="store_true")
    p.add_argument("--ready",action="store_true")
    args=p.parse_args()
    if args.check_pilot:
        tasks=json.loads((CODING/"tasks.json").read_bytes())
        official=json.loads((CODING/"tfidf_predictions.json").read_bytes())
        for t in [tasks[0],tasks[-1]]:
            row=infer(t)
            q=t["instance_id"]
            old=json.loads((CODING/"predictions"/(q+".json")).read_bytes())
            assert row["prior"]==old["fusion"] and row["tfidf"]==official[q] and row["chunk_inventory_sha256"]==old["chunk_inventory_sha256"]
            print(q,"matches pilot controls",flush=True)
    else:
        (ROOT/"predictions").mkdir(exist_ok=True)
        tasks=json.loads((ROOT/"tasks.json").read_bytes())
        ready=[t for t in tasks if (ROOT/"receipts"/(t["instance_id"]+".json")).exists()]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(process,ready if args.ready else tasks))
        if not args.ready or len(ready)==len(tasks):
            seal()

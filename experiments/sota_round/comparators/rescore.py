"""Replay released rankings/grade labels against official scoring metadata. No API calls."""

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from itertools import combinations
from pathlib import Path
from statistics import mean, median, quantiles
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
DATA_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/98d7416c24c778c2fee6e6f3006e7a073259d48f/longmemeval_s_cleaned.json"
DATA_SHA = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
PAPR = "https://raw.githubusercontent.com/Papr-ai/papr-longmemeval/3543e066f4a5f065f4e3d473f5a37a644d6a8881/"
GBRAIN = "https://raw.githubusercontent.com/garrytan/gbrain-evals/875573a5fdb1ca2e8e77fcbe65e2abf362308610/docs/benchmarks/2026-10-04-longmemeval-opaque-followups/1a-harness/"
QA_ARMS = ["high_k20_opus-4-6", "high_opus-4-6", "low_gpt-5-mini", "embed_gpt-5-mini"]


def download():
    files = {"papr_ranks.jsonl": PAPR + "retrieval/top5_sessions.jsonl"}
    for arm in QA_ARMS:
        files[f"papr_{arm}.grades.jsonl"] = PAPR + f"results/papr_{arm}.jsonl.eval-results-gpt-4o"
    for arm in ["A1", "A2"]:
        files[f"gbrain_{arm}.ndjson.gz"] = GBRAIN + f"{arm}/rows.ndjson.gz"
    for filename, url in files.items():
        with urlopen(url, timeout=120) as response:
            (ROOT / filename).write_bytes(response.read())
    with urlopen(DATA_URL, timeout=120) as response:
        data = response.read()
    assert hashlib.sha256(data).hexdigest() == DATA_SHA
    questions = json.loads(data)
    selected = ["question_id", "question_type", "answer_session_ids", "haystack_session_ids"]
    metadata = [{key: row[key] for key in selected} for row in questions]
    (ROOT / "official_scoring_metadata.json").write_text(json.dumps(metadata), encoding="utf8")


def jsonl(filename):
    path = ROOT / filename
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def key(rows):
    actual = [row for row in rows if "question_id" in row]
    indexed = {row["question_id"]: row for row in actual}
    assert len(indexed) == len(actual) == 500
    return indexed


def paired(a, b):
    assert a.keys() == b.keys()
    gained = sum(a[q] and not b[q] for q in a)
    lost = sum(b[q] and not a[q] for q in a)
    n = gained + lost
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(gained, lost) + 1)) / 2**n)
    return {"gained": gained, "lost": lost, "p_two_sided_exact": p}


def evaluate_rankings(qs, ranks, k):
    hits, rows = {}, []
    for qid, row in qs.items():
        if "_abs" in qid:
            continue
        gold = set(row["answer_session_ids"])
        retrieved = set(ranks[qid][:k])
        assert gold and retrieved <= set(row["haystack_session_ids"]) and gold <= set(row["haystack_session_ids"])
        hits[qid] = gold <= retrieved
        found = len(gold & retrieved)
        rows.append({"question_id": qid, "question_type": row["question_type"], "gold": len(gold), "found": found,
                     "recall_all": int(hits[qid]), "recall_any": int(found > 0), "fraction": found / len(gold)})
    assert len(rows) == 470
    return hits, rows


def aggregate(rows):
    return {"n": len(rows), "all_hits": sum(x["recall_all"] for x in rows), "any_hits": sum(x["recall_any"] for x in rows),
            "mean_fraction": mean(x["fraction"] for x in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="refetch pinned inputs and verify official dataset hash")
    if parser.parse_args().download:
        download()
    reference = key(json.loads((ROOT / "official_scoring_metadata.json").read_text(encoding="utf8")))
    papr = key(jsonl("papr_ranks.jsonl"))
    assert all(row["top5_session_ids"] == row["top20_session_ids"][:5] for row in papr.values())
    assert all(len(row["top20_session_ids"]) == 20 for row in papr.values())
    ranks = {"papr": {q: row["top20_session_ids"] for q, row in papr.items()}}
    for arm in ["A1", "A2"]:
        gb = key(jsonl(f"gbrain_{arm}.ndjson.gz"))
        assert all(set(row["answer_session_ids"]) == set(reference[q]["answer_session_ids"]) for q, row in gb.items())
        ranks[f"gbrain_{arm}"] = {q: [r["session_id"] for r in sorted(row["retrieved"], key=lambda x: x["rank"])] for q, row in gb.items()}
    all_results, per_row, all_hits = {}, [], {}
    types = sorted({x["question_type"] for x in reference.values()})
    for method, ranked in ranks.items():
        assert ranked.keys() == reference.keys()
        for k in ([1, 3, 5, 10, 20] if method == "papr" else [1, 3, 5]):
            label = f"{method}@{k}"
            all_hits[label], rows = evaluate_rankings(reference, ranked, k)
            all_results[label] = {"overall": aggregate(rows), "by_type": {
                t: aggregate([row for row in rows if row["question_type"] == t]) for t in types}}
            per_row.extend({"arm": label, **row} for row in rows)
    qa, qa_counts = {}, {}
    for arm in QA_ARMS:
        qs = key(jsonl(f"papr_{arm}.grades.jsonl"))
        assert qs.keys() == reference.keys()
        assert all(r["autoeval_label"]["model"] == "gpt-4o-2024-08-06" and isinstance(r["autoeval_label"]["label"], bool) for r in qs.values())
        labels = {q: r["autoeval_label"]["label"] for q, r in qs.items()}
        qa[arm] = labels
        qa_counts[arm] = {"overall": sum(labels.values()), "abstentions": sum(v for q, v in labels.items() if "_abs" in q),
                          "by_type_including_abstentions": {t: sum(v for q, v in labels.items() if reference[q]["question_type"] == t) for t in types}}
    latency = [x["rerank_latency_s"] for x in papr.values()]
    metadata = {"dataset_url": DATA_URL, "dataset_sha256": DATA_SHA,
                "evidence_count_distribution": dict(Counter(len(q["answer_session_ids"]) for q in reference.values() if "_abs" not in q["question_id"])),
                "n": len(reference), "retrieval_counts": all_results,
                "strict_at_5_paired": {f"{a} vs {b}": paired(all_hits[a], all_hits[b]) for a,b in combinations(["papr@5", "gbrain_A2@5", "gbrain_A1@5"],2)},
                "qa_recount": qa_counts, "qa_high_k20_vs_k5": paired(qa[QA_ARMS[0]], qa[QA_ARMS[1]]),
                "papr_published_rerank_latency_s": {"median": median(latency), "p90": quantiles(latency, n=10, method="inclusive")[8]}}
    (ROOT / "recount.json").write_text(json.dumps(metadata, indent=2), encoding="utf8")
    with (ROOT / "recount_per_question.csv").open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(per_row[0]))
        writer.writeheader()
        writer.writerows(per_row)
    print({k:v["overall"] for k,v in all_results.items()})
    print(metadata["strict_at_5_paired"], metadata["qa_high_k20_vs_k5"])
    print({k:v["overall"] for k,v in qa_counts.items()})


if __name__ == "__main__":
    main()

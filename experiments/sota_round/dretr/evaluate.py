"""Open labels only after a complete rankings file exists. Use the pinned official evaluator."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from rank import HERE, DATA_SHA, upstream_symbol, vector_key
from upstream.eval_utils import evaluate_retrieval


INDEX = upstream_symbol("process_item_flat_index", {})
METRICS = ("recall_all@1", "recall_all@3", "recall_all@5", "recall_all@10",
           "recall_any@5", "official_ndcg@5")


def summarize_binary(a, b, clusters):
    d = a.astype(float) - b
    wins = int(np.sum(d > 0))
    losses = int(np.sum(d < 0))
    draws = np.random.default_rng(20261116)
    boot = np.empty(20_000)
    cl_boot = np.empty_like(boot)
    unique, labels = np.unique(clusters, return_inverse=True)
    group_counts = np.bincount(labels)
    group_deltas = np.bincount(labels, weights=d)
    for i in range(0, len(boot), 1000):
        idx = draws.integers(len(d), size=(1000, len(d)))
        boot[i:i + 1000] = d[idx].mean(axis=1)
        groups = draws.integers(len(unique), size=(1000, len(unique)))
        cl_boot[i:i + 1000] = group_deltas[groups].sum(axis=1) / group_counts[groups].sum(axis=1)
    # Sparse discordances make percentile bootstrap intervals optimistic. Under
    # independent paired questions, the hit-rate difference is P(discordant) *
    # (2*P(win | discordant)-1). Exact binomial intervals at 97.5% each yield a
    # conservative joint 95% rectangle by Bonferroni, including adverse endpoints.
    n_discordant = wins + losses
    discord_ci = binomtest(n_discordant,len(d)).proportion_ci(.975)
    win_ci = binomtest(wins,n_discordant).proportion_ci(.975) if n_discordant else (0.,1.)
    corners = [p * (2*q-1) for p in discord_ci for q in win_ci]
    return dict(n=len(d), delta=d.mean(), wins=wins, losses=losses, ties=len(d)-wins-losses,
                ci95=list(np.quantile(boot,[.025,.975])),
                evidence_cluster_ci95=list(np.quantile(cl_boot,[.025,.975])),
                conservative_exact_ci95=[min(corners),max(corners)],
                exact_p=binomtest(wins, wins+losses).pvalue if wins+losses else 1.0)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("cache", type=Path)
    cli.add_argument("--ranks", type=Path, default=HERE / "ranks.jsonl")
    cli.add_argument("--out-dir", type=Path, default=HERE)
    args = cli.parse_args()
    dataset_path = args.cache / "longmemeval_s_cleaned.json"
    assert hashlib.file_digest(dataset_path.open("rb"), "sha256").hexdigest() == DATA_SHA
    data = json.loads(dataset_path.read_text("utf-8"))
    ranks = [json.loads(line) for line in args.ranks.read_text("utf-8").splitlines()]
    assert len(data) == len(ranks) == 500
    methods = list(ranks[0]["ranks"])
    records, dispositions = [], []
    parent = list(range(len(data)))
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    evidence_owner = {}
    for i, (x, r) in enumerate(zip(data, ranks)):
        assert r["row"] == i and r["query_sha256"] == vector_key(x["question"])
        assert len(x["haystack_sessions"]) == len(x["haystack_session_ids"]) == len(x["haystack_dates"])
        corpus_ids = []
        positive_hashes = set()
        has_user_evidence = False
        for sess, sid, date in zip(x["haystack_sessions"], x["haystack_session_ids"], x["haystack_dates"]):
            _, ids, _ = INDEX(sess, "session", sid, date)
            corpus_ids.extend(ids)
            positive_turns = [t["content"] for t in sess if t["role"] == "user" and t.get("has_answer", False)]
            has_user_evidence |= bool(positive_turns)
            positive_hashes.update(vector_key(t) for t in positive_turns)
            if positive_turns:
                positive_hashes.add(vector_key(" ".join(t["content"] for t in sess if t["role"] == "user")))
        gold = sorted({sid for sid in corpus_ids if "answer" in sid})
        status = ("abstention" if "_abs" in x["question_id"] else
                  "no_positive_user_turn" if not has_user_evidence else "scored")
        base = dict(row=i, question_id=x["question_id"], question_type=x["question_type"],
                    status=status, n_gold=len(gold), n_declared_gold=len(set(x["answer_session_ids"])), **r["costs"])
        dispositions.append(base)
        if status != "scored":
            continue
        assert gold
        for h in positive_hashes:
            if h in evidence_owner:
                parent[root(i)] = root(evidence_owner[h])
            else:
                evidence_owner[h] = i
        for method, order in r["ranks"].items():
            assert sorted(order) == list(range(len(corpus_ids)))
            rec = dict(row=i, question_id=x["question_id"], question_type=x["question_type"], method=method)
            for k in (1, 3, 5, 10):
                any_hit, all_hit, ndcg = evaluate_retrieval(order, gold, corpus_ids, k)
                rec[f"recall_all@{k}"] = int(all_hit)
                if k == 5:
                    rec["recall_any@5"] = int(any_hit)
                    rec["official_ndcg@5"] = float(ndcg)
            rec["positive_ranks"] = ",".join(str(j+1) for j,k in enumerate(order) if corpus_ids[k] in gold)
            records.append(rec)
    out = args.out_dir
    for filename, rows in (("dispositions.csv",dispositions),("per_question.csv",records)):
        with (out / filename).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    scored = [d for d in dispositions if d["status"] == "scored"]
    grouped = {m:[rec for rec in records if rec["method"]==m] for m in methods}
    metric = "recall_all@5"
    outcome = {m: np.array([r[metric] for r in group]) for m,group in grouped.items()}
    evidence_clusters = np.array([root(d["row"]) for d in scored])
    stats = {m:{key:float(np.mean([row[key] for row in group])) for key in METRICS}
             for m,group in grouped.items()}
    by_type = {}
    for t in sorted({x["question_type"] for x in scored}):
        ids = [i for i, x in enumerate(scored) if x["question_type"] == t]
        by_type[t] = {"n":len(ids), **{m:float(np.mean(s[ids])) for m,s in outcome.items()}}
    contrast = {m:summarize_binary(outcome["witness"], outcome[m], evidence_clusters)
                for m in methods if m != "witness"}
    summary = dict(dataset_sha256=DATA_SHA, protocol_sha256=hashlib.file_digest(
        (HERE/"PROTOCOL.md").open("rb"),"sha256").hexdigest(),
        rankings_sha256=hashlib.file_digest(args.ranks.open("rb"),"sha256").hexdigest(),
        rows=len(data), disposition_counts=dict(collections.Counter(x["status"] for x in dispositions)),
        n_evidence_clusters=len(set(evidence_clusters)),
        cluster_size_max=max(collections.Counter(evidence_clusters).values()),
        costs_scored_totals={k:sum(d[k] for d in scored) for k in ranks[0]["costs"]},
        costs_all_totals={k:sum(d[k] for d in dispositions) for k in ranks[0]["costs"]},
        scores=stats, successful_all5={m:int(s.sum()) for m,s in outcome.items()},
        paired_witness_minus=contrast, recall_all5_by_type=by_type)
    (out / "results.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()

"""Secondary endpoint over all non-abstentions, using release-declared session IDs."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from evaluate import HERE, vector_key
from upstream.eval_utils import evaluate_retrieval


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("cache", type=Path)
    cli.add_argument("--ranks", type=Path, default=HERE / "ranks.jsonl")
    args = cli.parse_args()
    data = json.loads((args.cache/"longmemeval_s_cleaned.json").read_text("utf-8"))
    ranks = [json.loads(s) for s in args.ranks.read_text("utf-8").splitlines()]
    assert len(data) == len(ranks) == 500
    output = []
    for i, (entry, rank) in enumerate(zip(data, ranks)):
        assert rank["row"] == i and rank["query_sha256"] == vector_key(entry["question"])
        if "_abs" in entry["question_id"]:
            continue
        ids = entry["haystack_session_ids"]
        gold = set(entry["answer_session_ids"])
        assert gold and gold.issubset(set(ids))
        for method, order in rank["ranks"].items():
            any_hit, all_hit, ndcg = evaluate_retrieval(order,gold,ids,5)
            output.append(dict(question_id=entry["question_id"],method=method,
                               any5=int(any_hit), all5=int(all_hit), official_ndcg5=float(ndcg)))
    with (HERE/"declared_gold_per_question.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output[0])
        writer.writeheader()
        writer.writerows(output)
    methods = list(ranks[0]["ranks"])
    groups = {m:[x for x in output if x["method"]==m] for m in methods}
    summary = dict(n=len(groups["witness"]), post_hoc_endpoint=True, scores={})
    for m, group in groups.items():
        summary["scores"][m] = {k:float(np.mean([x[k] for x in group])) for k in
                                 ("all5","any5","official_ndcg5")}
        for k in ("all5","any5"):
            summary["scores"][m][k+"_count"] = sum(x[k] for x in group)
    print(json.dumps(summary,indent=2))
    (HERE/"declared_gold_results.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")


if __name__ == "__main__":
    main()

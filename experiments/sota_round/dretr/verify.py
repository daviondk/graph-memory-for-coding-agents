"""Verify the frozen outputs, recompute counts, and score the verbatim FP32 reference."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from evaluate import HERE, INDEX, evaluate_retrieval, summarize_binary
from rank import vector_key


def read_csv(path):
    with path.open(encoding="utf-8",newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("cache",type=Path)
    args = cli.parse_args()
    primary = json.loads((HERE/"results.json").read_text("utf-8"))
    with (HERE/"ranks.jsonl").open("rb") as stream:
        assert hashlib.file_digest(stream,"sha256").hexdigest() == primary["rankings_sha256"]
    ledger = read_csv(HERE/"dispositions.csv")
    assert len(ledger) == 500
    per_question = read_csv(HERE/"per_question.csv")
    counts = {m:sum(int(x["recall_all@5"]) for x in per_question if x["method"]==m) for m in primary["scores"]}
    assert counts == primary["successful_all5"]
    assert collections.Counter(x["status"] for x in ledger) == primary["disposition_counts"]
    raw = json.loads((args.cache/"longmemeval_s_cleaned.json").read_text("utf-8"))
    exact = [json.loads(s) for s in (HERE/"contriever_original_ranks.jsonl").read_text("utf-8").splitlines()]
    witness = {x["question_id"]:int(x["recall_all@5"]) for x in per_question if x["method"]=="witness"}
    scored = []
    for i,(item, output, disposition) in enumerate(zip(raw,exact,ledger)):
        assert output["row"]==i and output["query_sha256"]==vector_key(item["question"])
        assert item["question_id"]==disposition["question_id"]
        if disposition["status"]=="abstention":
            continue
        ids = item["haystack_session_ids"]
        rank = output["ranks"]["contriever_original_fp32"]
        assert sorted(rank)==list(range(len(ids)))
        schemes = [("declared_470",ids,item["answer_session_ids"])]
        if disposition["status"]=="scored":
            user_ids = [INDEX(s,"session",c,d)[1][0] for s,c,d in zip(item["haystack_sessions"],ids,item["haystack_dates"])]
            schemes.append(("official_419",user_ids,[c for c in user_ids if "answer" in c]))
        for scheme, corpus, gold in schemes:
            any5, all5, ndcg = evaluate_retrieval(rank,gold,corpus,5)
            scored.append(dict(question_id=item["question_id"],scheme=scheme,any5=int(any5),all5=int(all5),official_ndcg5=ndcg))
    with (HERE/"contriever_original_per_question.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=scored[0])
        writer.writeheader()
        writer.writerows(scored)
    summary={}
    for scheme in ("official_419","declared_470"):
        group=[r for r in scored if r["scheme"]==scheme]
        summary[scheme] = dict(n=len(group),any5=sum(r["any5"] for r in group),all5=sum(r["all5"] for r in group),
                               official_ndcg5=float(np.mean([r["official_ndcg5"] for r in group])))
        if scheme=="official_419":
            a=np.array([witness[r["question_id"]] for r in group])
            b=np.array([r["all5"] for r in group])
            summary[scheme]["paired_witness_minus"]=summarize_binary(a,b,np.arange(len(a)))
            del summary[scheme]["paired_witness_minus"]["evidence_cluster_ci95"]
    (HERE/"contriever_original_results.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()

"""Audit cached Contriever ranks against the verbatim author routine on label-blind sample."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from transformers import AutoModel, AutoTokenizer

from rank import HERE, upstream_symbol, vector_key


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("cache", type=Path)
    cli.add_argument("--all", action="store_true", help="run the original retrieval branch for every question")
    args = cli.parse_args()
    data = json.loads((args.cache/"longmemeval_s_cleaned.json").read_text("utf-8"))
    expected = [json.loads(line) for line in (HERE/"ranks.jsonl").read_text("utf-8").splitlines()]
    impl = upstream_symbol("DenseRetrievalMaster",dict(np=np,torch=torch,DataLoader=DataLoader))
    runner = object.__new__(impl)
    path = args.cache/"contriever"
    runner.retriever_model = (AutoTokenizer.from_pretrained(path,local_files_only=True),
                              AutoModel.from_pretrained(path,local_files_only=True).eval().cuda())
    # Same hardware, more conservative numerical settings and the original per-query,
    # unsorted corpus batch. Sample chosen only by question text hash.
    torch.backends.cuda.matmul.allow_tf32 = False
    chosen = list(range(len(data))) if args.all else sorted(range(len(data)),key=lambda i:vector_key(data[i]["question"]))[:24]
    result = []
    exact_output = []
    for i in chosen:
        corpus = [" ".join(t["content"] for t in s if t["role"]=="user") for s in data[i]["haystack_sessions"]]
        order = runner.run_flat_retrieval(data[i]["question"],"flat-contriever",corpus).tolist()
        old = expected[i]["ranks"]["contriever_session"]
        result.append(dict(row=i, exact_top5=(order[:5]==old[:5]), set_top5=(set(order[:5])==set(old[:5])),
                           exact_full=(order==old), overlap5=len(set(order[:5]).intersection(old[:5]))))
        if args.all:
            exact_output.append(dict(row=i,query_sha256=vector_key(data[i]["question"]),
                                     ranks={"contriever_original_fp32":order},costs=expected[i]["costs"]))
            if i % 50 == 0:
                print("author routine",i,"/",len(data),flush=True)
    output = {"n":len(result),"exact_top5":sum(x["exact_top5"] for x in result),
              "same_top5_set":sum(x["set_top5"] for x in result),
              "exact_full":sum(x["exact_full"] for x in result),"sample":result}
    filename = "contriever_parity_all.json" if args.all else "contriever_parity.json"
    (HERE/filename).write_text(json.dumps(output,indent=2),encoding="utf-8")
    if args.all:
        (HERE/"contriever_original_ranks.jsonl").write_text("".join(json.dumps(row)+"\n" for row in exact_output),
                                                             encoding="utf-8")
    print({k:v for k,v in output.items() if k!="sample"})


if __name__ == "__main__":
    main()

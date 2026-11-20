"""Fetch versioned code, labels, public issue inputs, and the optional local Potion baseline."""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen
from cache_paths import CACHE, ROOT


def fetch(url, dest, expected=None):
    dest.parent.mkdir(exist_ok=True, parents=True)
    if not dest.exists():
        with urlopen(url, timeout=150) as response:
            dest.write_bytes(response.read())
    if expected and hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
        raise ValueError("Broken file checksum for " + str(dest))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--potion",action="store_true")
    options=p.parse_args()
    base = "https://raw.githubusercontent.com/Qiushao-E/SWE-Explore-Bench/5602f031f2d9562d0a805f83402b536e831a5a11/"
    for item in ["README.md","LICENSE","eval.py","eval_runner.py","explorers/__init__.py","explorers/base.py","explorers/bm25.py",
                 "explorers/chunking.py","explorers/rag_tfidf.py","explorers/rag_potion.py"]:
        fetch(base+item,ROOT/"upstream"/item)
    bench=ROOT/"bench.final.public.jsonl"
    fetch("https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench/resolve/bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9/bench.final.public.jsonl",
          bench,"dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202")
    source=ROOT/"verified.parquet"
    fetch("https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/78f471bf655a3137b2e8a75af1501690ec009ec3/data/test-00000-of-00001.parquet",
          source,"030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25")
    sys.path[:0] = [str(CACHE/"deps"), str(ROOT/"deps")]
    import pyarrow.parquet as pq
    verified = {r["instance_id"]:r for r in pq.read_table(source, columns=["instance_id","repo","base_commit","problem_statement"]).to_pylist()}
    grouped=defaultdict(list)
    for line in bench.read_bytes().splitlines():
        row=json.loads(line)
        iid=row["instance_id"]
        if row["dataset"]=="verified":
            grouped[iid.rsplit("-",1)[0]].append(iid)
    ids=[q for repo,group in sorted(grouped.items()) for q in sorted(group,key=lambda s:hashlib.sha256(("swe-localization-v1|"+s).encode()).hexdigest())[:2]]
    assert len(ids)==23 and len(grouped)==12
    (ROOT/"tasks.json").write_text(json.dumps([verified[q] for q in ids],indent=2),encoding="utf8")
    if options.potion:
        remote="https://huggingface.co/minishlab/potion-base-8M/resolve/bf8b056651a2c21b8d2565580b8569da283cab23/"
        for n in ["model.safetensors","tokenizer.json","tokenizer_config.json","special_tokens_map.json","config.json","modules.json","vocab.txt"]:
            fetch(remote+n,CACHE/"potion-base-8M"/n)
    print(len(ids),"locked issue inputs")


if __name__=="__main__":
    main()

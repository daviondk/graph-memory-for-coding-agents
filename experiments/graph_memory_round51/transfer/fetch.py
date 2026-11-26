"""Fetch the pinned HotpotQA training shards and official evaluator on demand."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import urllib.request

from study import P

REVISION = "1908d6afbbead072334abe2965f91bd2709910ab"
COMMIT = "fa3a36370899e1d85822de61e58c85ea19993154"
BASE = "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/" + REVISION
URLS = {
    **{f"train-{j:05d}-of-00002.parquet":f"{BASE}/distractor/train-{j:05d}-of-00002.parquet" for j in range(2)},
    "official.py":f"https://raw.githubusercontent.com/hotpotqa/hotpot/{COMMIT}/hotpot_evaluate_v1.py",
}


def fetch(item):
    name,url = item
    target = P/name
    if target.is_file():
        return
    temp=target.with_suffix(target.suffix+".part")
    request=urllib.request.Request(url,headers={"User-Agent":"agent-memory-research/1"})
    with urllib.request.urlopen(request,timeout=120) as reply,temp.open("wb") as out:
        shutil.copyfileobj(reply,out,1<<20)
    temp.replace(target)


if __name__=="__main__":
    P.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(fetch,URLS.items()))

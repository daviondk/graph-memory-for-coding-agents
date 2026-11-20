"""Restore public benchmark inputs pinned in the experiment receipt. No credentials."""
import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
IN=ROOT/"inputs"
HOT="https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/1908d6afbbead072334abe2965f91bd2709910ab/distractor/"
WIKI="https://huggingface.co/datasets/xanhho/2WikiMultihopQA/resolve/612bc5039a457880d9e7d84c3b0a4cf154b70e4f/"
MU="https://huggingface.co/datasets/bdsaglam/musique/resolve/22873a405dd809893b22ada0b499299fb612d2df/"
BEAM="https://raw.githubusercontent.com/canghongjian/beam_retriever/902980bfb5bd47a963569ab9c3621fd5ae81204a/"
FILES={
    "dev.parquet":HOT+"validation-00000-of-00001.parquet",
    "train-half.parquet":HOT+"train-00000-of-00002.parquet",
    "transfer-train-half.parquet":HOT+"train-00001-of-00002.parquet",
    "2wiki-dev.parquet":WIKI+"dev.parquet",
    "musique-dev.jsonl":MU+"musique_ans_v1.0_dev.jsonl",
    "beam-README.md":BEAM+"README.md",
    "beam.json":BEAM+"results/retrieval/hotpot_pred_best_retr.json",
    "musique-beam.json":BEAM+"results/retrieval/musique_pred_best.json",
    "2wiki-beam.json":BEAM+"results/retrieval/2wiki_pred_best.json",
}
def digest(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def main(check_only):
    IN.mkdir(exist_ok=True)
    expected=json.loads((ROOT/"transfer_lock.json").read_text(encoding="utf8"))["input_sha256"]
    for filename,url in FILES.items():
        path=IN/filename
        if not path.exists():
            if check_only:raise FileNotFoundError(path)
            part=path.with_suffix(path.suffix+".part")
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=120) as resp,part.open("wb") as f:
                shutil.copyfileobj(resp,f)
            assert digest(part)==expected[filename],filename
            part.replace(path)
        assert digest(path)==expected[filename],filename
        print(filename,expected[filename],flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--check-only",action="store_true")
    main(p.parse_args().check_only)

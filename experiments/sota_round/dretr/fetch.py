"""Download only the official benchmark and published checkpoints to a supplied cache."""
import argparse
import hashlib
import os
import shutil
import urllib.request
from pathlib import Path


DATASET = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/98d7416c24c778c2fee6e6f3006e7a073259d48f/"
CONTRIEVER = "https://huggingface.co/facebook/contriever/resolve/2bd46a25019aeea091fd42d1f0fd4801675cf699/"
STELLA = "https://huggingface.co/dunzhang/stella_en_1.5B_v5/resolve/7817065102fd9e1b031fe874e910c01f40b2f001/"
HASHES = {
    "longmemeval_s_cleaned.json":"d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442",
    "contriever/pytorch_model.bin":"d0b6e2516913f812360475154323f50e2b1e1da0ce6a435175e08f218784c6fb",
    "stella/model.safetensors":"222c4379b38c273e69e7e7ba7c68517ab8fef0bc92f8a5f557cf834f65046471",
}


def fetch(base, local, name, cache):
    dest = local / name
    digest = HASHES.get(dest.relative_to(cache).as_posix())
    dest.parent.mkdir(exist_ok=True,parents=True)
    if not dest.is_file():
        temp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(base + name, timeout=120) as source, temp.open("wb") as out:
            shutil.copyfileobj(source, out, length=1024*1024)
        if digest:
            with temp.open("rb") as f:
                assert hashlib.file_digest(f,"sha256").hexdigest() == digest, str(temp)
        os.replace(temp, dest)
    if digest:
        with dest.open("rb") as f:
            assert hashlib.file_digest(f,"sha256").hexdigest() == digest, str(dest)
    print(dest,flush=True)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("cache", type=Path)
    cli.add_argument("--stella", action="store_true")
    args = cli.parse_args()
    fetch(DATASET, args.cache, "longmemeval_s_cleaned.json", args.cache)
    for f in ("config.json","special_tokens_map.json","tokenizer.json","tokenizer_config.json",
              "vocab.txt","pytorch_model.bin"):
        fetch(CONTRIEVER, args.cache/"contriever", f, args.cache)
    if args.stella:
        for f in ("config.json","tokenization_qwen.py","modeling_qwen.py","special_tokens_map.json",
                  "tokenizer_config.json","tokenizer.json","vocab.json","merges.txt","added_tokens.json",
                  "2_Dense_1024/config.json","2_Dense_1024/model.safetensors","model.safetensors"):
            fetch(STELLA, args.cache/"stella", f, args.cache)


if __name__ == "__main__":
    main()

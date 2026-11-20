"""Cache Contriever embeddings for public benchmark text without using metadata or labels."""
import argparse
import hashlib
import json
import os
import platform
import time
from pathlib import Path

import numpy as np
import torch
import transformers
from transformers import AutoModel, AutoTokenizer


def key(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    parser.add_argument("--batch", type=int, default=32)
    args = parser.parse_args()
    torch.manual_seed(0)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    rows = json.loads((args.cache / "longmemeval_s_cleaned.json").read_text("utf-8"))
    queries = {row["question"] for row in rows}
    turns = set()
    sessions = set()
    for row in rows:
        for session in row["haystack_sessions"]:
            contents = [turn["content"] for turn in session if turn["role"] == "user"]
            turns.update(contents)
            sessions.add(" ".join(contents))
    del rows
    model = AutoModel.from_pretrained(args.cache / "contriever", local_files_only=True).eval().cuda()
    tokenizer = AutoTokenizer.from_pretrained(args.cache / "contriever", local_files_only=True)
    # Process the baseline and shared inputs first. The second block is needed for the
    # exhaustive turn control. Stage-two methods index only two selected turns per candidate.
    shared = set.union(queries, sessions)
    blocks = [("session", shared), ("extra-turn", turns - shared)]
    for tag, texts in blocks:
        meta_path = args.cache / f"vectors-{tag}.json"
        if meta_path.exists():
            continue
        texts = sorted(texts, key=lambda t: (len(t), key(t)))
        matrix = np.lib.format.open_memmap(args.cache / f"vectors-{tag}.npy", dtype=np.float32,
                                           mode="w+", shape=(len(texts), model.config.hidden_size))
        total_tokens = 0
        start = time.perf_counter()
        with torch.inference_mode():
            for i in range(0, len(texts), args.batch):
                batch = texts[i:i + args.batch]
                inputs = tokenizer(batch, padding=True, truncation=True, return_tensors="pt").to("cuda")
                output = model(**inputs).last_hidden_state
                mask = inputs.attention_mask.bool()
                pooled = output.masked_fill(~mask[..., None], 0.).sum(1) / mask.sum(1)[:, None]
                matrix[i:i + len(batch)] = pooled.cpu().numpy()
                total_tokens += int(mask.sum().item())
                if i % (args.batch * 100) == 0:
                    print(f"{tag}: {i}/{len(texts)}, {time.perf_counter() - start:.1f}s", flush=True)
        matrix.flush()
        seconds = time.perf_counter() - start
        metadata = dict(tag=tag, keys=[key(t) for t in texts], sentences=len(texts), tokens=total_tokens,
                        seconds=seconds, batch=args.batch, max_length=tokenizer.model_max_length,
                        gpu=torch.cuda.get_device_name(), torch=torch.__version__, numpy=np.__version__,
                        transformers=transformers.__version__, python=platform.python_version(),
                        peak_cuda_allocation_bytes=torch.cuda.max_memory_allocated(), tf32=True)
        temp = meta_path.with_suffix(".tmp")
        temp.write_text(json.dumps(metadata), encoding="utf-8")
        os.replace(temp, meta_path)
        print(tag, {k: v for k, v in metadata.items() if k != "keys"}, flush=True)


if __name__ == "__main__":
    main()

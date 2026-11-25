"""Rank anonymous records from the prepared public text view, without reference labels."""
import math
import os
import re
from collections import Counter
from pathlib import Path
import numpy as np
from prepare import ROOT, CACHE, read, dump, sha

WEIGHTS = "d0d559c47d5f71b1d280b13b62a2657f3e3bc70c0786f9ab91a36545e6a8f693"
MODEL = Path(os.environ.get("CONTRADOC_E5", "D:/CodexResearch/x20-isetrace-runtime/e5-base-v2"))
NEG = {"not", "never", "no", "none", "without", "neither", "nor", "cannot"}
TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:[.,]\d+)*")
def tokens(s):
    return TOKEN.findall(s.lower())
def features(parts):
    return (any(t in NEG or t.endswith("n't") for t in parts), {t for t in parts if t[0].isdigit()})
def lexical(query, docs):
    df = Counter(t for doc in docs for t in set(doc))
    n, mean = len(docs), max(1, sum(map(len, docs)) / len(docs))
    scores = []
    for doc in docs:
        counts = Counter(doc)
        k = 1.2 * (0.25 + 0.75 * len(doc) / mean)
        scores.append(sum(math.log1p((n - df[t] + .5) / (df[t] + .5))
                          * 2.2 * counts[t] / (counts[t] + k) for t in set(query) if t in counts))
    return scores
def encode(texts):
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(3)
    torch.set_num_interop_threads(1)
    assert sha((MODEL/"model.safetensors").read_bytes()) == WEIGHTS
    tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    model = AutoModel.from_pretrained(MODEL, local_files_only=True).cpu().eval()
    cache = CACHE / "embeddings"
    cache.mkdir(exist_ok=True)
    out = {}
    # Sorting by length reduces padding; the cache key fixes model, pooling and input string.
    pending = []
    for t in sorted(texts, key=lambda s: (len(s), s)):
        path = cache / (sha((WEIGHTS + "|mean-normalized-v1|" + t).encode()) + ".npy")
        if path.exists():
            out[t] = np.load(path, allow_pickle=False)
        else:
            pending.append((t, path))
    print("unique / to encode", len(texts), len(pending), flush=True)
    with torch.inference_mode():
        for start in range(0, len(pending), 24):
            block = pending[start:start+24]
            inp = tok([t for t, _ in block], padding=True, truncation=True, max_length=512, return_tensors="pt")
            x = model(**inp).last_hidden_state
            mask = inp["attention_mask"].unsqueeze(-1)
            vec = torch.nn.functional.normalize((x * mask).sum(1) / mask.sum(1), dim=1).numpy()
            for (t, path), v in zip(block, vec):
                assert v.shape == (768,) and np.isfinite(v).all()
                with path.with_suffix(".stage").open("wb") as f:
                    np.save(f, v)
                os.replace(path.with_suffix(".stage"), path)
                out[t] = v
            if start % 480 == 0:
                print("encoded", min(start + 24, len(pending)), flush=True)
    return out
def main():
    packet = CACHE / "packets.json.gz"
    assert sha(packet.read_bytes()) == read(ROOT/"input-lock.json")["packets"]
    rows = read(packet)
    texts = {("query: " + row["anchor"]) for row in rows}
    texts.update("passage: " + s for row in rows for _, s in row["records"])
    vec = encode(texts)
    out = []
    for row in rows:
        q = row["anchor"]
        ids, docs = zip(*row["records"])
        query, words = tokens(q), [tokens(s) for s in docs]
        scores = lexical(query, words)
        cos = np.stack([vec["passage: " + s] for s in docs]) @ vec["query: " + q]
        ix = range(len(docs))
        def sort(sc):
            return sorted(ix, key=lambda i: (-sc[i], i))
        bm, e5 = sort(scores), sort(cos)
        near = sorted(ix, key=lambda i: (abs(ids[i]), i))
        def fuse(*ranks):
            total = [0.] * len(docs)
            for rank in ranks:
                for k, i in enumerate(rank, start=1):
                    total[i] += 1 / (60 + k)
            return sort(total)
        hybrid, local = fuse(bm, e5), fuse(bm, e5, near)
        candidates = hybrid[1:5]
        polarity, numbers = features(query)
        def differs(i):
            neg, nums = features(words[i])
            return neg != polarity or bool(numbers and nums and nums != numbers)
        conflict = next((i for i in candidates if differs(i)), candidates[0])
        sham = min(candidates, key=lambda i: sha((row["id"] + "|" + str(ids[i]) + "|2219").encode()))
        adjacent = next(i for i in near if i != hybrid[0])
        policies = {"bm25": bm[:4], "e5": e5[:4], "hybrid": hybrid[:4], "local_fusion": local[:4],
                    "signature": [hybrid[0], conflict], "sham": [hybrid[0], sham], "neighbor": [hybrid[0], adjacent]}
        out.append({"id": row["id"], "picks": {p: [ids[i] for i in indices] for p, indices in policies.items()}})
    dump(ROOT/"forecasts.json.gz", out)
    dump(ROOT/"forecast-lock.json", {"rows": len(out), "source_lock": sha((ROOT/"input-lock.json").read_bytes()),
        "forecast": sha((ROOT/"forecasts.json.gz").read_bytes()), "predict": sha(Path(__file__).read_bytes()),
        "weights": WEIGHTS, "unique_inputs": len(texts)})
    print("sealed", len(out), flush=True)
if __name__ == "__main__":
    main()

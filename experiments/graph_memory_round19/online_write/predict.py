"""Query-blind capped online writes followed by BM25 on retained text only."""
import argparse
import gzip
import hashlib
import heapq
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
BASE = Path(os.environ.get("X20_DATA", "D:/CodexResearch"))
HERE = Path(__file__).resolve().parent
OLD = HERE.parent.parent / "graph_memory_round18" / "isetrace_e5"
CACHE = BASE / "x20-isetrace-e5-gpu/cache/projection"
RUNTIME = BASE / "x20-isetrace-runtime"
TOKENIZER = RUNTIME / "inputs/tokenizer.json"
sys.path.insert(0, str(RUNTIME / "upstream"))
from graph_memory.text.tokens import content_tokens
from rank_bm25 import BM25Okapi
from tokenizers import Tokenizer

CAPS = (4096, 8192, 16384)
POLICIES = ("fifo", "hash", "head", "ends", "output_head")

def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def stable(key):
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")

def stream_blocks(fields, pool, tokenizer):
    events = {}
    for unit in pool:
        meta = unit["metadata"]
        for span in unit["source_spans"]:
            eid = span["event_id"]
            event = (meta["message_index"], meta["sub_index"], meta["node_kind"],
                     eid, span["json_pointer"])
            if eid in events:
                assert events[eid] == event
            events[eid] = event
    addresses, blocks, keys = [], [], []
    unmatched = len(set(fields) - events.keys())
    for _, _, role, eid, pointer in sorted(events.values()):
        raw = fields[eid]
        offsets = tokenizer.encode(raw, add_special_tokens=False).offsets
        if not offsets:
            continue
        cuts = sorted({0, len(raw), *(a for a, _ in offsets[64::64])})
        pieces = [raw[a:b] for a, b in zip(cuts, cuts[1:])]
        costs = [len(x.ids) for x in tokenizer.encode_batch(pieces, add_special_tokens=False)]
        ev = len(addresses)
        addresses.append([eid, pointer])
        evhash = stable(eid)
        for j, (a, b, cost) in enumerate(zip(cuts, cuts[1:], costs)):
            if cost == 0:
                continue
            index = len(blocks)
            blocks.append([ev, a, b, cost, len(pieces[j].encode())])
            keys.append(((-index, 0), (stable(f"{eid}/{j}"), 0), (j, evhash),
                         (min(2*j, 2*(len(costs)-1-j)+1), evhash),
                         (j if role == "content.tool_output" else 2*j, evhash)))
    return addresses, blocks, keys, unmatched

def select(costs, keys, policy, cap):
    heap, used = [], 0
    for i, cost in enumerate(costs):
        stage, tie = keys[i][policy]
        heapq.heappush(heap, (-stage, -tie, -i, i))
        used += cost
        while used > cap:
            removed = heapq.heappop(heap)[-1]
            used -= costs[removed]
    return sorted(entry[-1] for entry in heap)

def read(keep, costs, lex, questions):
    corpus = [lex[i] for i in keep]
    model = BM25Okapi(corpus) if any(corpus) else None
    reads = {}
    for qid, tokens in questions:
        scores = model.get_scores(tokens) if model else [0.0] * len(keep)
        order = sorted(range(len(keep)), key=lambda j: (-scores[j], keep[j]))
        selected, used = [], 0
        for j in order:
            i = keep[j]
            if used + costs[i] <= 2048:
                selected.append(i)
                used += costs[i]
                if used == 2048:
                    break
        reads[qid] = selected
    return reads

def forecast(row, tokenizer):
    addresses, blocks, keys, unmatched = stream_blocks(row["fields"], row["pool"], tokenizer)
    costs = [b[3] for b in blocks]
    # Cache per-fragment lexical analysis; corpus statistics are fitted anew only on keep.
    lex = [content_tokens(row["fields"][addresses[e][0]][a:b]) for e,a,b,_,_ in blocks]
    questions = [(qid, content_tokens(q)) for qid,q in row["q"]]
    arms = {}
    for cap in CAPS:
        for ip, pol in enumerate(POLICIES):
            keep = select(costs, keys, ip, cap)
            assert sum(costs[i] for i in keep) <= cap
            arms[f"{pol}/{cap}"] = [keep, read(keep, costs, lex, questions)]
    keep = list(range(len(costs)))
    arms["all"] = [None, read(keep, costs, lex, questions)]
    return dict(t=row["t"], addresses=addresses, blocks=blocks, unmatched=unmatched, arms=arms)

def worker(shard):
    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    path = HERE / f"forecast-{shard}.jsonl.gz"
    tmp = path.with_suffix(".part")
    count = 0
    with gzip.open(tmp, "wt", compresslevel=3, encoding="utf-8") as out:
        for source in sorted(CACHE.glob(f"{shard}-*.json.gz")):
            with gzip.open(source, "rt", encoding="utf-8") as f:
                item = forecast(json.load(f), tokenizer)
            out.write(dump(item) + "\n")
            count += 1
    tmp.replace(path)
    print("shard", shard, "trajectories", count, flush=True)
    return count

def run(workers):
    h = hashlib.sha256()
    paths = sorted(CACHE.glob("*.json.gz"))
    for p in paths:
        h.update(p.name.encode() + b"\0" + bytes.fromhex(digest(p)))
    expected = json.loads((OLD / "inventory.json").read_text(encoding="utf-8"))["projection_digest"]
    assert len(paths) == 1207 and expected == h.hexdigest()
    lock = dict(projection=expected, tokenizer=digest(TOKENIZER), predict=digest(Path(__file__)),
                protocol=digest(HERE / "PROTOCOL_RU.md"), n_trajectories=len(paths))
    (HERE / "input-lock.json").write_text(dump(lock), encoding="utf-8")
    with ProcessPoolExecutor(workers) as pool:
        counts = list(pool.map(worker, range(8)))
    assert sum(counts) == 1207
    lock["forecasts"] = {p.name:digest(p) for p in sorted(HERE.glob("forecast-*.jsonl.gz"))}
    (HERE / "forecast-lock.json").write_text(dump(lock), encoding="utf-8")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    run(parser.parse_args().workers)


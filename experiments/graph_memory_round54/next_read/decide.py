"""Replay one additional source read after an archived strict-context run."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
import re
import tarfile

HERE = Path(__file__).resolve().parent
DEFAULT_CACHE = Path("D:/CodexResearch/x20-r54-trace-choice")
BASE = "https://huggingface.co/datasets/eyuansu71/agent_retrieval_bench/resolve/5901e1ee3aff048290db72edf9c63bc498b79ea3/releases/"
CORPUS = "agent_retrieval_bench.tar.zst"
TRACES = "agent_retrieval_bench_gpt54mini_strict_context_trajectories.tar.zst"
EXCLUDED = {
    "01323034afde8983e978b8d2", "f39b3eb29d5ba2f6c18b0555",
    "35154a761b37d4f5767d1cfa", "0f88458fc1fe4acce078ce3f", "8b6ab1ba0883ff8104d28524",
}
METHODS = {
    "lexical": "lexical_all_files", "repomap": "repomap_all_files",
    "embed4": "Qwen3-Embedding-4B", "embed8": "Qwen3-Embedding-8B",
    "pplx": "pplx-embed-v1-4b", "nomic": "nomic-embed-code", "jina": "jina-code-embeddings-0.5b",
}
FUSION = ("lexical", "repomap", "embed4")
PATH_FIELD = re.compile(rb'"path"\s*:\s*("(?:[^"\\]|\\.)*")')
def hexdigest(data):
    return sha256(data).hexdigest()

def file_hash(p):
    with p.open("rb") as f:
        return __import__("hashlib").file_digest(f, "sha256").hexdigest()

def save(name, obj):
    data = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()+b"\n"
    (HERE/name).write_bytes(gzip.compress(data, mtime=0) if name.endswith(".gz") else data)

def read_file(p):
    data = p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix == ".gz" else data)

def source_files(cache):
    from urllib.request import urlopen
    cache.mkdir(parents=True, exist_ok=True)
    subdirs = {CORPUS:"agent_retrieval_bench/", TRACES:"trajectories/agent_retrieval_bench_gpt54mini_strict_context/"}
    digests = {}
    for name, subdir in subdirs.items():
        url = BASE+subdir+name
        expected = urlopen(url+".sha256", timeout=30).read().decode().split()[0]
        path = cache/name
        if not path.exists():
            from shutil import copyfileobj
            import tempfile
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as temp:
                partial = Path(temp.name)
                try:
                    with urlopen(url, timeout=90) as response:
                        copyfileobj(response, temp, length=1024*1024)
                except BaseException:
                    temp.close()
                    partial.unlink(missing_ok=True)
                    raise
            try:
                assert file_hash(partial) == expected
                partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
        digests[name] = file_hash(path)
        assert digests[name] == expected
    return digests

def original_runs(cache):
    """Whitelist decision inputs from trace members and original rankers."""
    traces = {}
    with tarfile.open(cache/TRACES) as arc:
        for member in arc:
            if "/traces_" not in member.name or not member.isfile():
                continue
            row = json.load(arc.extractfile(member))
            q = row["sample_id"]
            assert q not in traces
            given = []
            for key in ("given_file", "given_files", "path", "implementation_files", "anchor_file"):
                value = row["query"].get(key, [])
                given.extend([value] if isinstance(value, str) else value)
            traces[q] = dict(repo=row["repo"], commit=row["base_commit"], raw=row["raw_final_files"],
                             strict=row["final_files"], reads=row["read_paths"], given=given, ranks={})
    counts = Counter()
    filenames = {method+"_details.jsonl": short for short,method in METHODS.items()}
    with tarfile.open(cache/CORPUS, "r|zst") as arc:
        for member in arc:
            method = filenames.get(Path(member.name).name)
            if not method:
                continue
            for line in arc.extractfile(member):
                item = json.loads(line)
                q = item["sample_id"]
                trace = traces[q]
                assert (trace["repo"], trace["commit"]) == (item["repo"], item["base_commit"])
                assert method not in trace["ranks"]
                trace["ranks"][method] = item["top_files"][:20]
                kind = item["task_type"]
                assert kind == trace.setdefault("task", kind)
                counts[method] += 1
    assert len(traces) == 287 and all(counts[m] == len(traces) for m in METHODS)
    panel = {q:t for q,t in traces.items() if q not in EXCLUDED and t["task"] != "abstention"}
    return panel, dict(Counter(t["task"] for t in traces.values())), sorted(set(traces) & EXCLUDED)

def first_chunks(cache, traces):
    required = defaultdict(set)
    for t in traces.values():
        key = (t["repo"].replace("/", "__"), t["commit"])
        required[key].update(t["raw"])
        for seq in t["ranks"].values():
            required[key].update(seq)
    chunks = {}
    with tarfile.open(cache/CORPUS, "r|zst") as arc:
        for member in arc:
            p = Path(member.name)
            if not p.name.endswith(".chunks.jsonl"):
                continue
            key = (p.parent.name, p.name.split(".")[0])
            if key not in required:
                continue
            assert key not in chunks
            matches = chunks[key] = {}
            for line in arc.extractfile(member):
                attr = PATH_FIELD.search(line)
                assert attr
                path = json.loads(attr[1])
                if path not in required[key]:
                    continue
                doc = json.loads(line)
                assert (doc["repo"].replace("/", "__"), doc["base_commit"], doc["path"]) == (*key, path)
                order = (doc["start_line"], doc["end_line"], doc["chunk_id"])
                if path not in matches or order < matches[path][0]:
                    matches[path] = (order, hexdigest(doc["text"].encode()))
    assert set(chunks) == set(required)
    return chunks

def choose(t, available):
    old, opened = set(t["strict"]), set(t["reads"])
    assert old <= opened
    blocked = opened | set(t["given"])
    def eligible(paths):
        return [p for p in dict.fromkeys(paths) if p in available and p not in blocked]
    candidates = {name:eligible(t["ranks"][name]) for name in METHODS}
    scores = Counter()
    for name in FUSION:
        for rank, path in enumerate(t["ranks"][name], start=1):
            if path in candidates[name]:
                scores[path] += 1/(60 + rank)
    ordered = sorted(scores, key=lambda p: (-scores[p], p))
    assert ordered
    fusion = ordered[0]
    suggestions = [p for p in dict.fromkeys(t["raw"]) if p not in blocked]
    valid = eligible(suggestions)
    first = valid[0] if valid else None
    chosen = {"fusion":fusion, "memory":first or fusion,
              "confirmed":next((p for p in valid if p in scores), fusion)}
    for name, pool in candidates.items():
        chosen[name] = pool[0] if pool else fusion
        chosen["memory_"+name] = first or chosen[name]
    def pid(p):
        return hexdigest((t["repo"]+"\0"+p).encode())
    receipts = {pid(p):[available[p][0][0], available[p][0][1], available[p][1]] for p in set(chosen.values())}
    return dict(repo=t["repo"],commit=t["commit"],task=t["task"],strict=sorted(map(pid,old)),
                opened=sorted(map(pid,opened)),original_suggestions=len(suggestions),missing=len(set(suggestions)-set(valid)),
                new_suggestions=list(map(pid,valid)),chosen={k:pid(v) for k,v in chosen.items()},receipts=receipts)

def main(cache):
    digests=source_files(cache)
    traces, counts, exclusions=original_runs(cache)
    receipts=first_chunks(cache,traces)
    decisions = {q:choose(t,receipts[(t["repo"].replace("/", "__"),t["commit"])]) for q,t in sorted(traces.items())}
    save("decisions.json.gz", decisions)
    save("decision-seal.json", dict(sources=digests, counts=counts, excluded=exclusions,
         n=len(decisions),protocol=file_hash(HERE/"PROTOCOL_RU.md"), code=file_hash(Path(__file__)),
         decisions=file_hash(HERE/"decisions.json.gz")))
    print("Sealed",len(decisions),counts,flush=True)

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--cache",type=Path,default=DEFAULT_CACHE)
    main(cli.parse_args().cache)

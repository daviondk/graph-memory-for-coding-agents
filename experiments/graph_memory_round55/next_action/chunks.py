"""Stream only first-chunk metadata for the sealed decision pool."""
import argparse
import hashlib
import json
import re
import tarfile
from collections import defaultdict
from pathlib import Path

from inputs import HERE, R54, DEFAULT_ARCHIVE, address, digest, read, save

PATH = re.compile(rb'"path"\s*:\s*("(?:[^"\\]|\\.)*")')
CORPUS = "agent_retrieval_bench.tar.zst"


def extract(corpus):
    expected = read(R54 / "next_read/decision-seal.json")["sources"][CORPUS]
    assert digest(corpus) == expected
    seal = read(HERE / "prediction-seal.json")
    assert digest(HERE / "decisions.json.gz") == seal["decisions.json.gz"]
    assert digest(HERE / "oof-scores.json.gz") == seal["oof-scores.json.gz"]
    data = read(R54 / "learned_read/projection.json.gz")
    obs = read(HERE / "observations.json.gz")
    dec = read(HERE / "decisions.json.gz")
    scores = read(HERE / "oof-scores.json.gz")
    required, panels, outputs = defaultdict(set), {}, {}
    seen = set()
    for q, v in scores.items():
        selected = set(dec[q]["embed4_fixed"])
        for ranker in ("static", "snapshot", "history", "rrf7"):
            selected.update(sorted(range(len(v[ranker])), key=lambda j: -v[ranker][j])[:2])
        paths = data[q]["paths"]
        key = obs[q]["repo"], obs[q]["commit"]
        panels[q] = sorted(selected)
        required[key].update(paths[i] for i in selected)
    with tarfile.open(corpus, "r|zst") as tree:
        for member in tree:
            p = Path(member.name)
            if not p.name.endswith(".chunks.jsonl"):
                continue
            repo, commit = p.parent.name.replace("__","/"), p.name.split(".")[0]
            key = repo, commit
            if key not in required:
                continue
            assert key not in seen
            seen.add(key)
            path_ids, first = {}, {}
            for row in tree.extractfile(member):
                hit = PATH.search(row)
                assert hit
                encoded_path = hit[1]
                if encoded_path not in path_ids:
                    path_ids[encoded_path] = address(repo, json.loads(encoded_path))
                pid = path_ids[encoded_path]
                if pid not in required[key]:
                    continue
                chunk = json.loads(row)
                assert chunk["repo"] == repo and chunk["base_commit"] == commit and address(repo, chunk["path"]) == pid
                order = (chunk["start_line"], chunk["end_line"], chunk["chunk_id"])
                if pid not in first or order < first[pid][0]:
                    body = chunk["text"].encode()
                    first[pid] = order, len(body), hashlib.sha256(body).hexdigest()
            assert set(first) == required[key]
            outputs[key] = first
    assert seen == set(required)
    result = {}
    for q, ids in panels.items():
        receipts = outputs[obs[q]["repo"], obs[q]["commit"]]
        result[q] = {str(i): receipts[data[q]["paths"][i]] for i in ids}
    save("first-chunks.json.gz", result)
    save("byte-registration.json", dict(protocol=digest(HERE / "BYTE_PROTOCOL_RU.md"),
         predictions=digest(HERE / "prediction-seal.json"), corpus=expected, extractor=digest(HERE / "chunks.py"),
         costs=digest(HERE / "first-chunks.json.gz"), optimizer=digest(HERE / "byte_budget.py")))
    print("snapshots", len(seen), "decisions",sum(map(len,panels.values())),flush=True)


if __name__ == "__main__":
    arg = argparse.ArgumentParser()
    arg.add_argument("--corpus", type=Path, default=DEFAULT_ARCHIVE.parent / CORPUS)
    extract(arg.parse_args().corpus)

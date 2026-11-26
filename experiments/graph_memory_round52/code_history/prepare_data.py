"""Validate archived inputs and extract only addresses of observed editor actions."""
from collections import Counter
from pathlib import Path, PurePosixPath
import ast
import gzip
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
CACHE = Path("D:/CodexResearch/x20-bench-workspace/work/graph_memory_round3")
R37 = EXP / "graph_memory_round37/code_visibility"
R27 = EXP / "graph_memory_round27/code_boundary/prepare.py"

def digest(value):
    return hashlib.sha256(value).hexdigest()

def sha(path):
    return digest(path.read_bytes())

def save(name, value):
    data = (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
    (HERE / name).write_bytes(gzip.compress(data, mtime=0) if name.endswith(".gz") else data)

def read(path):
    path = Path(path)
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

def production_filter():
    # Use precisely the two definitions pinned in R27, without running unrelated preprocessing.
    tree = ast.parse(R27.read_text(encoding="utf-8-sig"))
    definitions = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "prod")
                   or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "RISK")]
    assert len(definitions) == 2
    scope = {"PurePosixPath": PurePosixPath, "re": re}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(R27), "exec"), scope)
    return scope["prod"]

def compact(meta, events):
    # Assign successive IDs on first observation. Never sort names using future information.
    files, dirs, directory, names, sequence = {}, {}, [], [], []
    last_time = -1
    for at, kind, path in events:
        assert at >= last_time
        last_time = at
        ident = -1
        if path is not None:
            if path not in files:
                files[path] = len(files)
                parent = str(PurePosixPath(path).parent)
                dirs.setdefault(parent, len(dirs))
                directory.append(dirs[parent])
                names.append(digest(path.encode()))
            ident = files[path]
        sequence.append((at, kind, ident))
    return {**meta, "directory": directory, "paths_sha256": names, "events": sequence}

def main():
    prod = production_filter()
    pinned = {"r27": sha(R27), "r37": sha(R37 / "events.json.gz")}
    assert pinned["r37"] == read(R37 / "manifest.json")["files"]["events.json.gz"]
    original = read(R37 / "events.json.gz")
    train, test, excluded = [], [], []
    for run, obj in original.items():
        events = []
        for e in obj["events"]:
            at, kind = e[:2]
            if kind == "read" and e[-1] > 0 and prod(e[2]):
                events.append((at, "R", e[2]))
            elif kind == "edit" and e[3].get("matched") and prod(e[2]):
                events.append((at, "E", e[2]))
            elif kind in ("barrier", "other"):
                events.append((at, "B", None))
        train.append(compact({"run": run, "issue": obj["issue"], "repo": obj["repo"]}, events))
    train_issues = {r["issue"] for r in train}
    panels = ["real_swe", "real_swe_followup"]
    seen = set()
    for panel in panels:
        catalog = read(EXP / "graph_memory_round3" / panel / "download_summary.json")["sources"]
        for name, checksum in sorted(catalog.items()):
            f = CACHE / panel / name
            assert sha(f) == checksum
            pinned[panel + "/" + name] = checksum
            with gzip.open(f, "rt", encoding="utf-8") as src:
                for line in src:
                    obj = json.loads(line)
                    issue = obj["instance"]
                    assert issue not in seen
                    seen.add(issue)
                    if issue in train_issues:
                        excluded.append(issue)
                        continue
                    events = []
                    for at, (tool, args, obs) in enumerate(obj["events"]):
                        cmd = args.get("command")
                        path = args.get("path", "").removeprefix("/testbed/").removeprefix("./")
                        if tool == "other" or cmd not in ("view", "str_replace", "insert", "create", "undo_edit"):
                            events.append((at, "B", None))
                        elif prod(path):
                            if cmd == "str_replace" and obs.startswith("The file snapshot has been edited."):
                                events.append((at, "E", path))
                            elif cmd == "view" and re.search(r"(?m)^ *[0-9]+\t", obs):
                                events.append((at, "R", path))
                    test.append(compact({"run": issue, "issue": issue, "repo": obj["official_repo"],
                                         "panel": panel}, events))
    assert len(seen) == 293 and len(train) == 3307 and len(train_issues) == 37
    save("train_trace.json.gz", train)
    save("test_trace.json.gz", test)
    save("sources.json", {"sha256": pinned, "excluded_overlap": sorted(excluded),
                          "training_runs": len(train), "training_issues": len(train_issues),
                          "test_issues": len(test), "all_test_issues": len(seen)})
    print("validated", len(train), len(train_issues), len(test), len(excluded))

if __name__ == "__main__":
    main()


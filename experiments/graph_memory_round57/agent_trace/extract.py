"""Project genuine SWE-agent observables to names, integer line-content identities and byte lengths."""
import argparse
from collections import Counter
import gzip
from hashlib import file_digest, md5, sha256
import json
from pathlib import Path, PurePosixPath
import re
import shlex

HERE = Path(__file__).resolve().parent
COHORT = HERE.parents[1] / "graph_memory_round16/anchor_transfer/cohort.json"
DEFAULT = Path("D:/CodexResearch/x20-anchor-transfer/trajectories")
HEADER = re.compile(r"^\[File: ([^\n]+?) \((\d+) lines? total\)\]\r?$", re.M)
LINE = re.compile(r"^(\d+):(.*)$")
EXPR = re.compile(r"[;&|$`><\r\n]")
NAV = {"open", "goto", "scroll_up", "scroll_down", "find_file", "search_dir", "search_file", "pwd", "ls", "cd"}


def save(path, data):
    raw = (json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=True) + "\n").encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def digest(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def classify(command):
    if not command or EXPR.search(command):
        return "barrier"
    try:
        parts = shlex.split(command)
    except ValueError:
        return "barrier"
    if not parts or parts[0] not in NAV:
        return "barrier"
    return parts[0]


def project(raw, repo):
    classes = Counter()
    stream = []
    lines_seen = {}
    for step in json.loads(raw)["trajectory"]:
        action = classify((step.get("action") or "").strip())
        classes[action] += 1
        event = [action]
        if action in ("open", "goto", "scroll_up", "scroll_down"):
            output = step.get("observation") or ""
            header = HEADER.search(output)
            if header:
                p = PurePosixPath(header[1])
                if (len(p.parts) >= 3 and p.parts[0] == "/" and p.parts[1] in ("testbed", repo.replace("/", "__"))
                        and ".." not in p.parts):
                    lines = []
                    for line in output[header.end():].splitlines():
                        match = LINE.fullmatch(line)
                        if match:
                            contents = (match[2] + "\n").encode("utf-8")
                            identifier = lines_seen.setdefault(contents, len(lines_seen))
                            lines.append([int(match[1]), identifier, len(contents)])
                    if lines and all(b[0] == a[0] + 1 for a, b in zip(lines, lines[1:])):
                        event.extend([str(PurePosixPath(*p.parts[2:])), lines])
        stream.append(event)
    return stream, dict(classes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT)
    args = parser.parse_args()
    cohort = read(COHORT)["tasks"]
    result = []
    sources = []
    for child, task in sorted(cohort.items()):
        for model, obj in sorted(task["trajectories"].items()):
            raw = (args.archive_dir / model / (child + ".json")).read_bytes()
            assert md5(raw).hexdigest() == obj["etag"]
            projected, counts = project(raw, task["repo"])
            result.append({"issue": child, "actor": model, "repo": task["repo"], "events": projected})
            sources.append({"issue": child, "actor": model, "key": obj["key"], "sha256": sha256(raw).hexdigest(),
                            "md5": obj["etag"], "classes": counts})
    save(HERE / "prefixes.json.gz", result)
    save(HERE / "sources.json", {"cohort_sha256": digest(COHORT), "sources": sources,
                                  "archive_origin": "https://swe-bench-submissions.s3.amazonaws.com/"})
    print(f"{len(result)} traces projected and source identities verified.")


if __name__ == "__main__":
    main()

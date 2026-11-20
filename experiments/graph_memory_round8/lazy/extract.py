"""Input-only literals aligned to the prefiltered Round 7 observation roster."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
R7 = WORK / "graph_memory_round7/online/search"


def rows(path):
    with gzip.open(path, "rt", encoding="utf8") as fp:
        for line in fp:
            yield json.loads(line)


def pack(x):
    return json.dumps(x, ensure_ascii=True, separators=(",", ":")).encode()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for data in iter(lambda: fp.read(2**20), b""):
            h.update(data)
    return h.hexdigest()


def write_json(name, obj):
    (ROOT / name).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf8")


def checked(p):
    p = p.removeprefix("/testbed/").removeprefix("./")
    if p.endswith(".py") and not p.startswith("/") and ".." not in p.split("/"):
        return p


PATH = re.compile(r"""(?<![\w./$-])((?:/testbed/|\./)?[A-Za-z0-9_][\w./-]*\.py)(?=$|[\s"';|()])""")
READ = re.compile(r"(?:^|[|;&])\s*(?:cat|sed|nl|head|tail|awk)\b")
SED = re.compile(r"""\bsed\s+-n\s+['"]?([1-9]\d*),([1-9]\d*)p(?:['"]|\s|$)""")
CD = re.compile(r"(?:^|[;&\n])\s*(?:cd|pushd|popd)\b")


def request(ev, args, extra, cwd):
    if not ev or ev[0] not in ("view", "shell"):
        return
    path = limits = None
    if ev[0] == "view":
        path = checked(str(args.get("path", "")))
        limits = args.get("view_range")
    else:
        cmd = (extra or {}).get("command", "")
        if not READ.search(cmd) or CD.search(cmd) or "$" in cmd or chr(96) in cmd or ">" in cmd:
            return
        paths = set(PATH.findall(cmd))
        if len(paths) == 1:
            literal = paths.pop()
            if cwd or literal.startswith("/testbed/"):
                path = checked(literal)
                matches = SED.findall(cmd)
                if len(matches) == 1:
                    limits = list(map(int, matches[0]))
    if path != ev[1]:
        return
    if not (isinstance(limits, list) and len(limits) == 2 and
            all(type(x) is int for x in limits) and 0 < limits[0] <= limits[1]):
        limits = None
    return [path, limits]


def main():
    obs = [R7 / "observations.jsonl.gz", R7 / "followup/independent.jsonl.gz"]
    roster = {q["id"]: q for f in obs for q in rows(f)}
    ids = set()
    used = set(obs)
    p5 = WORK / "graph_memory_round5"
    ext = WORK / "graph_memory_round6/version/external"
    sources = [(ext/"source.gz", ext/"terminal.gz", "claude")]
    sources += [(p5 / f"action_transfer/source_{k}.gz", p5 / f"action_transfer/terminal_{k}.gz", "kimi") for k in range(8)]
    independent = p5 / "action_probe/raw_pairs.jsonl.gz"
    used.add(independent)
    terms = {i: t for i, t in rows(independent) if i in roster and roster[i]["panel"] == "kimi_replication"}
    sources += [(p5 / f"writer/source_{k}.jsonl.gz", None, "kimi_replication") for k in range(8)]
    with gzip.GzipFile(str(ROOT / "observations.gz"), mode="wb", mtime=0) as out:
        for f, term, panel in sources:
            used.add(f)
            terminal = iter(rows(term)) if term else None
            if term:
                used.add(term)
            for task in rows(f):
                iid = task["instance"]
                if terminal:
                    tid, t = next(terminal)
                    assert tid == iid
                if iid not in roster or panel != roster[iid]["panel"]:
                    continue
                if not terminal:
                    t = terms[iid]
                q = roster[iid]
                assert iid not in ids
                ids.add(iid)
                cwd = True
                requests = []
                for ev, (_, args, _), extra in zip(q["events"], task["events"], t, strict=True):
                    requests.append(request(ev, args, extra, cwd))
                    if extra and CD.search(extra["command"]):
                        cwd = bool(re.fullmatch(r"\s*cd\s+/testbed/?\s*", extra["command"]))
                q["requests"] = requests
                out.write(pack(q) + b"\n")
            if terminal:
                assert next(terminal, None) is None
    assert ids == set(roster)
    write_json("inputs.json", {"sources": {p.relative_to(WORK).as_posix(): digest(p) for p in sorted(used)},
               "files": {s: digest(ROOT / s) for s in ["PROTOCOL_RU.md", "observations.gz", "extract.py"]},
               "tasks": len(roster)})


if __name__ == "__main__":
    main()

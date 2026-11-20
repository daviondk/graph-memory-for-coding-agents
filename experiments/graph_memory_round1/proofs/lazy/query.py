"""Operate the lazy import memory in separate processes.

python query.py record REPO OLD source.module target.module cache.json --method historical
python query.py recall REPO NEW cache.json
python query.py direct REPO NEW source.module target.module
The cache is a trusted local certificate created by record. It is never loaded as code.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter

from lazy_git import GitObjects, Snapshot, METHODS, record, direct, check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("direct", "record", "recall"):
        child = sub.add_parser(action)
        child.add_argument("repo")
        child.add_argument("commit")
        if action in ("direct","record"):
            child.add_argument("source")
            child.add_argument("target")
        if action in ("record","recall"):
            child.add_argument("cache", type=Path)
        if action == "record":
            child.add_argument("--method", choices=METHODS, default="short3")
    args = parser.parse_args()
    if not args.commit or any(ord(c) < 32 for c in args.commit):
        parser.error("Git commit specification must be one nonempty line")
    if args.action != "recall" and (args.source == args.target or
            not all(p.isidentifier() for arg in (args.source,args.target) for p in arg.split("."))):
        parser.error("Expected two distinct dotted Python module names")
    begin = perf_counter()
    obj = GitObjects(args.repo)
    try:
        snap = Snapshot(obj, args.commit)
        if args.action == "direct":
            output = {"answer": direct(snap, args.source, args.target)}
        elif args.action == "record":
            cache, extra = record(snap, args.source, args.target, args.method)
            with args.cache.open("x", encoding="utf8") as f:
                json.dump(cache, f, ensure_ascii=True, separators=(",",":"))
            # The enumerator is bounded by the frozen 10k path-prefix write budget.
            # Empty results are answered by exhaustive bounded BFS if enumeration capped.
            answer = bool(cache["proofs"]) or (extra["capped"] and direct(snap, args.source, args.target))
            output = {"answer": answer, "proof_count": len(cache["proofs"]), "record": extra}
        else:
            cache = json.loads(args.cache.read_text(encoding="utf8"))
            answer, fast, valid = check(snap, cache)
            output = {"answer": answer, "metadata_only": fast, "certificate_sufficient": valid}
        print(json.dumps({**output,"measurement":snap.describe(),"seconds":perf_counter()-begin},ensure_ascii=True))
    finally:
        obj.close()


if __name__ == "__main__":
    main()

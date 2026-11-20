"""Post-run audit. Replay all saved outputs, then independently check each trace."""
import csv
import gzip
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

from analyze import analyze
from experiment import HERE, simulate, verify_seal


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack_mask(value):
    number = int(value, 16)
    return {k for k in range(32) if (1 << k) & number}


def audit(directory):
    key = lambda r: (int(r["seed"]), int(r["rho"]), r["tool"])
    builds = {key(r): r for r in json.loads((directory / "builds.json").read_bytes())}
    requests = {}
    phases = Counter()
    with gzip.open(directory / "jobs.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        for r in csv.DictReader(stream):
            seed, rho, step = int(r["seed"]), int(r["rho"]), int(r["step"])
            parsed = set(map(int, r["role_ordered_keys"].split(".")))
            assert parsed == unpack_mask(r["query_mask"])
            assert int(r["stream"]) == seed*100 + {"fit":1, "validation":2, "test":3}[r["phase"]]
            phases[r["phase"]] += 1
            if r["phase"] == "test":
                assert (seed,rho,step) not in requests
                requests[seed,rho,step] = parsed
    visits = Counter()
    with gzip.open(directory / "steps.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        for r in csv.DictReader(stream):
            seed, rho, tool = key(r)
            test_key = (seed, rho, int(r["step"]))
            config = builds[seed,rho,tool]
            request, cache = requests[test_key], unpack_mask(config["caches"][r["policy"]])
            assert request == unpack_mask(r["query_mask"]) and cache == unpack_mask(r["cache_mask"])
            assert len(cache) == 8 and len(config["snapshot_uint32"]) == 32
            missing = request - cache
            assert missing == unpack_mask(r["missing_mask"])
            needed = missing if tool=="field" else {k//4 for k in missing}
            actions = list(map(int,r["actions"].split("."))) if r["actions"] else []
            if tool == "block":
                full_order = sorted(needed, key=lambda s: (-sum(k//4==s for k in missing),s))
                returned = {s*4+k for s in actions for k in range(4)}
            else:
                full_order, returned = sorted(needed), set(actions)
            assert actions == full_order[:2] and returned == unpack_mask(r["returned_mask"])
            answered = request & (cache | returned)
            assert answered == unpack_mask(r["answer_mask"])
            assert (len(needed),len(actions),len(returned),int(answered==request)) == \
                   tuple(map(int, (r["required_reads"],r["actual_reads"],r["returned_values"],r["correct"])))
            visits[test_key + (r["tool"],r["policy"])] += 1
    assert len(visits) == len(requests)*10 == 245760 and set(visits.values()) == {1}
    assert phases == {"fit":18432,"validation":9216,"test":24576}
    return phases, len(visits)


if __name__ == "__main__":
    verify_seal()
    published = HERE / "results"
    with tempfile.TemporaryDirectory(prefix="repeat-",dir=HERE) as temporary:
        replay = Path(temporary)
        simulate(replay)
        analyze(replay)
        for name in ("builds.json","jobs.csv.gz","steps.csv.gz","worlds.csv","summary.json","examples.json"):
            assert digest(replay/name) == digest(published/name), name
            print(digest(published/name), name)
    phases, rows = audit(published)
    print("Audited query phases:", dict(phases), "policy rows:", rows)

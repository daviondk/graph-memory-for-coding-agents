"""Static compaction of an observed snapshot and stochastic held-out lookup jobs."""
import csv
import gzip
import hashlib
import io
import json
import random
import struct
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES, ROLES, CAPACITY, READ_LIMIT = 8, 4, 8, 2
WORLDS = tuple(916001 + n for n in range(64))
CONDITIONS = (0, 50, 100)
TOOLS = ("block", "field")
BASELINES = ("marginal", "whole_block", "recent", "validation_choice")
POLICIES = ("joint",) + BASELINES
PHASES = (("fit", 96, 1), ("validation", 48, 2), ("test", 128, 3))


def derived(seed, part):
    return seed * 100 + part


def mask(keys):
    return sum(1 << key for key in set(keys))


def bits(code):
    while code:
        bit = code & -code
        yield bit.bit_length() - 1
        code ^= bit


def world(seed):
    rng = random.Random(derived(seed, 0))
    popularity = rng.uniform(0.7, 1.5)
    mixture = [(rank + 1) ** -popularity for rank in range(SOURCES)]
    order = list(range(SOURCES))
    rng.shuffle(order)
    layout = []
    for role in range(ROLES):
        physical = order.copy()
        for _ in range(1 + rng.randrange(3)):
            left, right = rng.sample(range(SOURCES), 2)
            physical[left], physical[right] = physical[right], physical[left]
        layout.append(physical)
    role_weights = [1.0, 0.85, 0.65, 0.45]
    rng.shuffle(role_weights)
    values = [rng.getrandbits(32) for _ in range(SOURCES * ROLES)]
    return mixture, layout, role_weights, values


def make_jobs(seed, part, n, rho, world_data):
    mixture, layout, role_weights, _ = world_data
    rng = random.Random(derived(seed, part))
    jobs = []
    for _ in range(n):
        width = rng.choices((2, 3, 4), weights=(0.33, 0.45, 0.22))[0]
        role_order = sorted(range(ROLES), key=lambda role: rng.expovariate(role_weights[role]))
        shared = rng.choices(range(SOURCES), weights=mixture)[0]
        independent = rng.choices(range(SOURCES), weights=mixture, k=ROLES)
        coupled = rng.random() < rho / 100
        keys = tuple(ROLES * layout[role][shared if coupled else independent[role]] + role
                     for role in role_order[:width])
        jobs.append(keys)
    return jobs


def blocks_for(keys):
    result = {}
    for key in keys:
        source = key // ROLES
        result[source] = result.get(source, 0) | (1 << (key % ROLES))
    return result


def learned(history, tool):
    counts = Counter(key for job in history for key in job)
    marginal = mask(sorted(range(SOURCES * ROLES), key=lambda k: (-counts[k], k))[:CAPACITY])
    last_seen = {key: position for position, key in enumerate(k for job in history for k in job)}
    recent = mask(sorted(range(SOURCES * ROLES), key=lambda k: (-last_seen.get(k, -1), k))[:CAPACITY])
    patterns = [Counter() for _ in range(SOURCES)]
    for job in history:
        for source, submask in blocks_for(job).items():
            patterns[source][submask] += 1
    def gain(source, kept):
        if tool == "field":
            return sum(counts[source * ROLES + role] for role in bits(kept))
        return sum(n for asked, n in patterns[source].items() if asked & ~kept == 0)
    full = (1 << ROLES) - 1
    selected = sorted(range(SOURCES), key=lambda s: (-gain(s, full), s))[:CAPACITY // ROLES]
    whole = sum(full << (s * ROLES) for s in selected)
    # (benefit, negative global mask) gives the same lowest-ID tie break as marginal.
    table = {0: (0, 0)}
    for source in range(SOURCES):
        nxt = {}
        for keep in range(1 << ROLES):
            size, benefit = keep.bit_count(), gain(source, keep)
            key_mask = keep << (source * ROLES)
            for used, (old_benefit, neg_mask) in table.items():
                if used + size <= CAPACITY:
                    candidate = (old_benefit + benefit, neg_mask - key_mask)
                    nxt[used + size] = max(candidate, nxt.get(used + size, (-1, 0)))
        table = nxt
    joint = -table[CAPACITY][1]
    if tool == "field":
        assert joint == marginal, "Additive read contract must reduce to marginal frequency"
    return {"marginal": marginal, "whole_block": whole, "recent": recent, "joint": joint}


def units(missing, tool):
    if tool == "field":
        return [(k, 1 << k) for k in bits(missing)]
    by_source = blocks_for(bits(missing))
    return [(s, ((1 << ROLES) - 1) << (s * ROLES))
            for s in sorted(by_source, key=lambda s: (-by_source[s].bit_count(), s))]


def choose_benchmark(fit, validation, tool):
    candidates = learned(fit, tool)
    sums = {}
    for name in BASELINES[:3]:
        cache = candidates[name]
        sums[name] = sum(len(units(mask(job) & ~cache, tool)) for job in validation)
    return min(sums, key=sums.get), sums


@contextmanager
def gz_csv(path, columns):
    with path.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0,
                                               compresslevel=7) as gz, io.TextIOWrapper(gz, encoding="utf-8",
                                                                                       newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns.split())
        yield writer


def hexmask(number):
    return f"{number:08x}"


def simulate(dest):
    dest.mkdir(parents=True, exist_ok=True)
    jobs_path, traces_path = dest / "jobs.csv.gz", dest / "steps.csv.gz"
    configs = []
    with gz_csv(jobs_path, "seed rho phase step stream role_ordered_keys query_mask") as joblog, \
         gz_csv(traces_path, "seed rho tool policy step query_mask cache_mask missing_mask actions returned_mask "
                              "answer_mask required_reads actual_reads returned_values correct") as log:
        for seed in WORLDS:
            wd = world(seed)
            mixture, layout, role_weights, db = wd
            for rho in CONDITIONS:
                phases = {}
                for phase, n, part in PHASES:
                    phases[phase] = make_jobs(seed, part, n, rho, wd)
                    for step, job in enumerate(phases[phase]):
                        joblog.writerow((seed, rho, phase, step, derived(seed, part), ".".join(map(str, job)),
                                         hexmask(mask(job))))
                for tool in TOOLS:
                    winner, scores = choose_benchmark(phases["fit"], phases["validation"], tool)
                    caches = learned(phases["fit"] + phases["validation"], tool)
                    caches["validation_choice"] = caches[winner]
                    configs.append(dict(seed=seed, dataset="synthetic_rank_lookup_v1", rho=rho, tool=tool,
                                        world_stream=derived(seed, 0), snapshot_uint32=db, rank_weights=mixture,
                                        rank_to_source=layout, role_weights=role_weights, validation_scores=scores,
                                        validation_choice=winner, caches={k: hexmask(v) for k, v in caches.items()},
                                        build_slots=CAPACITY, writes_during_test=0,
                                        snapshot_source_reads=(SOURCES if tool=="block" else SOURCES*ROLES)))
                    for name in POLICIES:
                        cache = caches[name]
                        stored = {k: db[k] for k in bits(cache)}
                        packed = b"".join(struct.pack(">BI", k, value) for k, value in stored.items())
                        assert len(packed) == CAPACITY * 5
                        for step, job in enumerate(phases["test"]):
                            asked = mask(job)
                            missing = asked & ~cache
                            available = {k: stored[k] for k in job if k in stored}
                            required = units(missing, tool)
                            actions = required[:READ_LIMIT]
                            returned = 0
                            for _, group in actions:
                                for k in bits(group):
                                    if asked & (1 << k):
                                        available[k] = db[k]
                                returned |= group
                            success = all(k in available and available[k] == db[k] for k in job)
                            assert success == (len(required) <= READ_LIMIT)
                            log.writerow((seed,rho,tool,name,step,hexmask(asked),hexmask(cache),hexmask(missing),
                                          ".".join(str(unit) for unit, _ in actions),hexmask(returned),
                                          hexmask(mask(available)),len(required),len(actions),returned.bit_count(),
                                          int(success)))
    (dest / "builds.json").write_bytes((json.dumps(configs, separators=(",",":")) + "\n").encode())


def verify_seal():
    sealed = json.loads((HERE / "frozen.json").read_text(encoding="utf-8-sig"))
    for filename, expected in sealed["sha256"].items():
        assert hashlib.sha256((HERE / filename).read_bytes()).hexdigest() == expected, filename


if __name__ == "__main__":
    verify_seal()
    simulate(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "results")

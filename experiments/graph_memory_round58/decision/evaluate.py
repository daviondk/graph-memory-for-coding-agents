"""Replay causal checkpoint decisions on archived SQLite work counters."""
import argparse
from collections import defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACTIONS = ("cold", "demand", "full")
MODES = {"cold": "cold", "demand": "demand1024", "full": "full"}
CUTS = (0, 1, 4, 16)
GROUPS = ("0", "1-4", "5-16", "17+")


def load(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as file:
            return json.load(file)
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decide(n_past_queries):
    """Only observation visible to the primary actor at checkpoint time."""
    return "demand" if n_past_queries > 0 else "cold"


def best(cost):
    return min(ACTIONS, key=cost.__getitem__)


def ties(cost):
    return [a for a in ACTIONS if cost[a] == min(cost.values())]


def horizon_bin(h):
    if h == 0:
        return "0"
    if h <= 4:
        return "1-4"
    if h <= 16:
        return "5-16"
    return "17+"


@dataclass(frozen=True)
class Arm:
    useful: int
    padding: int
    receipt: int
    work: tuple

    @property
    def pre(self):
        return tuple(row for row in self.work if row[0] == 0)

    @property
    def reads(self):
        return tuple(row[3] + row[5] for row in self.work if row[0] != 0)

    def cost(self, horizon, padded=False):
        return 2 * (self.useful + self.padding * padded) + self.receipt + sum(self.reads[:horizon])


def old_inputs():
    root = HERE.parent / "restart"
    rows = load(root / "runs.json.gz")["runs"]
    audit = load(root / "audit.json")["projects"]
    cases = defaultdict(dict)
    for r in rows:
        if r["method"] not in MODES.values():
            continue
        name = next(k for k, v in MODES.items() if v == r["method"])
        key = (r["project"], r["panel"])
        st = r["stats"]
        assert st["snapshot_load"] == st["snapshot_write"]
        work = tuple(tuple([q[0], *q[2:]]) for q in r["queries"])
        arm = Arm(st["snapshot_useful"], st["snapshot_write"]-st["snapshot_useful"],
                  st["receipt_bytes"], work)
        gold = audit["/".join(reversed(key))]
        assert len(arm.reads) == gold["post_q"]
        assert arm.cost(len(arm.reads), True) == gold["arms"][r["method"]]["charged_bytes"]
        if name in cases[key]:
            assert cases[key][name] == arm
        cases[key][name] = arm
    return cases


def external_inputs():
    root = HERE.parent / "restart_transfer"
    cases = {}
    groups = {}
    data = load(root / "runs.json.gz")["projects"]
    for key, project in data.items():
        group, repo = key.split("/", 1)
        groups[repo] = group
        for workload, w in project["workloads"].items():
            arms = {}
            for name, method in MODES.items():
                record = w["arms"][method]
                s = record["summary"]
                arm = Arm(s["useful"], s["written"] - s["useful"], s["receipt"],
                          tuple(tuple(r) for r in record["work"]))
                assert arm.cost(len(arm.reads), True) == s["charged"]
                assert len(arm.reads) == s["post"] and len(arm.pre) + len(arm.reads) == s["queries"]
                arms[name] = arm
            cases[(repo, workload)] = arms
    return cases, groups


def slice_cases(cases):
    out = []
    for (repo, workload), arms in sorted(cases.items()):
        cold = arms["cold"]
        assert all(a.pre == cold.pre and len(a.reads) == len(cold.reads) for a in arms.values())
        assert all(a.padding >= 0 for a in arms.values())
        assert all(arms[x].padding == 0 for x in ("cold", "full"))
        observed, post = len(cold.pre), len(cold.reads)
        for h in sorted(set([post, *(min(v, post) for v in CUTS)])):
            costs = {name: a.cost(h) for name, a in arms.items()}
            padded = {name: a.cost(h, True) for name, a in arms.items()}
            out.append(dict(repo=repo, workload=workload, pre=observed, post=post, h=h,
                            primary=decide(observed), costs=costs, padded=padded,
                            oracle=ties(costs), padded_oracle=ties(padded)))
    return out


def fit(rows):
    def fit_action(items):
        return best({a: sum(x["costs"][a] for x in items) for a in ACTIONS})
    fixed = fit_action([x for x in rows if x["h"] == x["post"]])
    fallback = fit_action(rows)
    rule = {}
    for g in GROUPS:
        items = [x for x in rows if horizon_bin(x["h"]) == g]
        rule[g] = dict(n=len(items), action=fit_action(items) if items else fallback)
    return dict(fixed=fixed, fallback=fallback, buckets=rule)


def with_actions(rows, model):
    for x in rows:
        x["actions"] = {**{a:a for a in ACTIONS}, "primary":x["primary"],
                        "fixed":model["fixed"],
                        "given_horizon":model["buckets"][horizon_bin(x["h"])]["action"]}
        x["bytes"] = {k:x["costs"][a] for k,a in x["actions"].items()}
        x["bytes"]["oracle"] = min(x["costs"].values())


def block(rows):
    output = {}
    for name in rows[0]["bytes"]:
        d = [r["bytes"][name] - r["bytes"]["cold"] for r in rows]
        regret = [r["bytes"][name] - r["bytes"]["oracle"] for r in rows]
        output[name] = dict(bytes=sum(r["bytes"][name] for r in rows),
                            regret=sum(regret), max_regret=max(regret), wins=sum(v<0 for v in d),
                            ties=d.count(0), losses=sum(v>0 for v in d))
    for name in ("primary", "demand"):
        output[name]["padded_bytes"] = sum(r["padded"][r["actions"][name]] for r in rows)
        output[name]["padded_regret"] = sum(r["padded"][r["actions"][name]] -
                                             min(r["padded"].values()) for r in rows)
    return output


def contrasts(rows):
    # Two possible continuation lengths for the very same observed prefix.
    pairs = {}
    for x in rows:
        case = x["repo"] + "/" + x["workload"]
        parts = pairs.setdefault(case, {})
        if x["h"] == 0:
            parts["empty"] = x
        if x["h"] == x["post"]:
            parts["whole"] = x
    examples = []
    for case, item in pairs.items():
        z, f = item["empty"], item["whole"]
        regret = {a:[r["costs"][a] - min(r["costs"].values()) for r in (z,f)] for a in ACTIONS}
        examples.append(dict(case=case, pre=f["pre"], post=f["post"],
                             incompatible=not set(z["oracle"]).intersection(f["oracle"]),
                             minimax_pure=min(max(d) for d in regret.values()),
                             equal_mix_min_mean_regret=min(sum(d) for d in regret.values()) / 2,
                             regrets=regret))
    return examples


def run():
    old = old_inputs()
    new, groups = external_inputs()
    assert len(old) == 9 and len(new) == 24
    assert not set(r for r,w in old).intersection(r for r,w in new)
    rows = {"initial":slice_cases(old), "transfer":slice_cases(new)}
    model = fit(rows["initial"])
    for sample in rows.values():
        with_actions(sample, model)
    outcome = {}
    for split, sample in rows.items():
        final = [x for x in sample if x["post"] == x["h"]]
        outcome[split] = {}
        for label, sub in [("all",sample), *((w,[x for x in sample if x["workload"] == w])
                                             for w in sorted(set(x["workload"] for x in sample)))]:
            if sub:
                outcome[split][label] = {str(k):block([x for x in sub if x["h"] == min(k,x["post"])])
                                         for k in CUTS}
                outcome[split][label]["full"] = block([x for x in sub if x["h"] == x["post"]])
        if split == "transfer":
            for group in sorted(set(groups.values())):
                outcome[split][group] = {"full":block([x for x in final if groups[x["repo"]] == group])}
    base = HERE.parent
    hashes = {p.relative_to(base).as_posix():digest(p) for p in [base/"restart"/"runs.json.gz",
              base/"restart"/"audit.json",base/"restart_transfer"/"runs.json.gz"]}
    raw = dict(protocol_sha256_lf=hashlib.sha256((HERE/"PROTOCOL_RU.md").read_text(
               encoding="utf-8").encode()).hexdigest(), source_sha256=hashes,
               transfer_training_projects=sorted(set(r for r,w in old)), policies=model, rows=rows,
               continuation_pairs={s:contrasts(v) for s,v in rows.items()})
    return raw, outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    raw, totals = run()
    for filename, data in (("outcomes.json.gz",raw), ("results.json",totals)):
        path = HERE / filename
        if args.verify:
            assert data == load(path)
        elif path.suffix == ".gz":
            path.write_bytes(gzip.compress(json.dumps(data, sort_keys=True, separators=(",",":")).encode(),
                                           compresslevel=9, mtime=0))
        else:
            path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for key in totals:
        print(key, {k:v["bytes"] for k,v in totals[key]["all"]["full"].items()})
    print(raw["policies"])


if __name__ == "__main__":
    main()

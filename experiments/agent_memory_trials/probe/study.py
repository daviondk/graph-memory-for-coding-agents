"""Usage: python study.py {prepare,freeze,observe,score,verify}. See PROTOCOL.md."""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import sys

from tools_fixture import FAMILIES, execute

ROOT = Path(__file__).resolve().parent
ARMS = ("discriminating", "ordinary", "fresh")
SEED_SOURCE = 97319478
SEED_TARGET = 518447061
SEED_SCHEDULE = 94779311


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(name):
    return json.loads((ROOT / name).read_text("utf-8"))


def dump(name, obj):
    (ROOT / name).write_text(json.dumps(obj, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def lines(name, records):
    (ROOT / name).write_text("".join(json.dumps(row,ensure_ascii=True) + "\n" for row in records),encoding="utf-8")


def filehash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source():
    rng = random.Random(SEED_SOURCE)
    alt_sources = set(rng.sample(list(FAMILIES), 3))
    axes = [1, 1, 2, 2, 3, 3]
    rng.shuffle(axes)
    histories = {}
    for (name, spec), axis in zip(FAMILIES.items(), axes):
        old, recent = (0, axis) if name in alt_sources else (axis, 0)
        inputs = [spec["routine"]] * 4 + spec["edges"][:]
        rng.shuffle(inputs)
        events = [{"input": x, "previous": execute(name, old, x), "latest": execute(name, recent, x)} for x in inputs]
        # Selection uses exclusively the two historical builds' cassette.
        diagnostic = next(event for event in events if event["previous"] != event["latest"])
        modal = collections.Counter(inputs).most_common(1)[0][0]
        usual = next(event for event in events if event["input"] == modal)
        def compact(event):
            return {"input": event["input"], "output": event["latest"]}
        histories[name] = {"historical_modes": [old,recent], "cassette": events,
                           "discriminating": compact(diagnostic), "ordinary": compact(usual)}
    return histories


def make_targets(sources):
    rng = random.Random(SEED_TARGET)
    sched = random.Random(SEED_SCHEDULE)
    families = list(FAMILIES)
    sched.shuffle(families)
    blocks = [[], [], [], []]
    cases = {}
    for index, name in enumerate(families):
        old, recent = sources[name]["historical_modes"]
        modes = [old, recent]
        rng.shuffle(modes)
        tests = [rng.sample(pool,2) for pool in FAMILIES[name]["tests"]]
        for twin, mode in enumerate(modes):
            cid = f"T{rng.getrandbits(32):08X}"
            heldout = [pool[twin] for pool in tests]
            rng.shuffle(heldout)
            axis = max(old,recent)
            assert len({tuple(execute(name, m, x) for x in heldout) for m in range(4)}) == 4
            cases[cid] = {"family": name, "mode": mode, "source_mode": recent, "axis": axis,
                          "stable": mode == recent, "heldout": heldout}
            blocks[index // 3 * 2 + twin].append(cid)
    for block in blocks:
        sched.shuffle(block)
    layouts = [{"arm": arm, "block": i+1, "cases": block} for i, block in enumerate(blocks) for arm in ARMS]
    sched.shuffle(layouts)
    for i, row in enumerate(layouts):
        row["id"] = f"P{i+1:02d}"
    return cases, layouts


def records(row, cases, sources, observations=None):
    xs = []
    for cid in row["cases"]:
        case = cases[cid]
        fam = case["family"]
        obj = {"id":cid, "manual":FAMILIES[fam]["manual"]}
        if row["arm"] != "fresh":
            obj["one_archived_call_from_an_earlier_release"] = sources[fam][row["arm"]]
        if observations is not None:
            obj["only_observation_on_current_release"] = observations[cid]
            obj["pending_application_inputs"] = case["heldout"]
        xs.append(obj)
    return json.dumps(xs,ensure_ascii=True,separators=(",",":"))


CONTEXT = (
    "Each independent service below has one fixed current behavior from its manual. "
    "The listed default and each single alternative are the possible complete behaviors. "
    "An archived call, when supplied, came from an earlier release that may agree with the current one or differ. "
    "Your objective is to produce the correct outputs of a future application workload on the current release. "
    "All strings must be at most 64 Unicode code points. Treat each service independently. "
)
ACTION = (
    "Select exactly ONE valid scalar input for each service. You may invent any valid input or reuse an archived input. "
    "Think about how to distinguish the possible current behaviors with a single observation. You may combine features within a valid input. "
    "The harness will run each proposal on its current service and return its output. "
    'Respond with a single JSON object mapping every service id directly to your chosen scalar input. Services follow.\n'
)
DECIDE = (
    "Use the current observation and manual. For each service predict the exact JSON scalar output for each pending "
    "application input in the given order. Your four predictions will be compared to real execution on this release. "
    'Respond with a single JSON object mapping every service id directly to an array of four JSON scalar predictions. Services follow.\n'
)


def prepare():
    assert not (ROOT/"freeze.json").exists(), "sealed: copy to a new directory for a new design"
    sources = build_source()
    dump("source_history.json", sources)
    cases, plan = make_targets(sources)
    dump("targets_hidden.json",cases)
    dump("allocation.json",plan)
    lines("stage1.jsonl", [{"id":r["id"],"prompt":CONTEXT+ACTION+records(r,cases,sources)} for r in plan])


SEALED = ["study.py","tools_fixture.py","PROTOCOL.md","source_history.json","targets_hidden.json","allocation.json","stage1.jsonl","../shared/run_model.py"]


def compute_hashes():
    return {f:filehash(ROOT/f) for f in SEALED}


def freeze():
    assert not (ROOT / "freeze.json").exists()
    assert not (ROOT / "runs1").exists() and not (ROOT / "runs2").exists()
    dump("freeze.json", {"freeze_utc":now(), "sha256":compute_hashes(),"interpreter":sys.version,
                        "seeds":{"source":SEED_SOURCE,"target":SEED_TARGET,"schedule":SEED_SCHEDULE}})


def verify():
    assert read("freeze.json")["sha256"] == compute_hashes(), "freeze checksum mismatch"


def fetch_run(stage, rid):
    return read(f"runs{stage}/{rid}.json")


def decode(run):
    if run["status"] != "ok":
        return {}, run["status"]
    try:
        parsed = json.loads(run["text"])
    except (ValueError, TypeError):
        return {}, "invalid_json"
    if not isinstance(parsed, dict):
        return {}, "expected_mapping"
    return parsed, "ok"


def observe():
    verify()
    cases, sources = read("targets_hidden.json"), read("source_history.json")
    observations, requests = [], []
    for row in read("allocation.json"):
        run = fetch_run(1,row["id"])
        actions, stage_status = decode(run)
        returned = {}
        for cid in row["cases"]:
            case = cases[cid]
            probe = actions.get(cid)
            status = stage_status
            diagnostic, reproduced = False,False
            obs = {"input":probe}
            if stage_status == "ok":
                try:
                    if cid not in actions:
                        raise ValueError("missing probe")
                    obs["output"] = execute(case["family"],case["mode"],probe)
                    status = "executed"
                    diagnostic = execute(case["family"],case["axis"],probe) != execute(case["family"],0,probe)
                    reproduced = probe == sources[case["family"]]["discriminating"]["input"]
                except (TypeError,ValueError) as err:
                    obs["error"] = str(err)
                    status = "invalid_probe"
            else:
                obs["error"] = "no valid action returned"
            returned[cid] = obs
            observations.append({"id":row["id"],"block":row["block"],"arm":row["arm"],"case":cid,
                                 "family":case["family"],"observed_utc":now(),"status":status,"observation":obs,
                                 "separates_historical_alternatives":diagnostic,"replayed_archived_discriminator":reproduced,
                                 "overlaps_heldout":probe in case["heldout"]})
        requests.append({"id":row["id"],"prompt":CONTEXT+DECIDE+records(row,cases,sources,returned)})
    dump("observations.json",observations)
    lines("stage2.jsonl", requests)


def summary_units(rows, key):
    ans = {}
    for group in sorted(set(r[key] for r in rows)):
        subset = [r for r in rows if r[key] == group]
        ans[str(group)] = {a: sum(r["perfect"] for r in subset if r["arm"] == a) for a in ARMS}
        ans[str(group)]["cases_per_arm"] = sum(r["arm"] == "fresh" for r in subset)
    return ans


def score():
    verify()
    cases = read("targets_hidden.json")
    observations = {(x["id"],x["case"]):x for x in read("observations.json")}
    rows, resources = [], []
    for req in read("allocation.json"):
        run = fetch_run(2,req["id"])
        answers, status = decode(run)
        for st in (1,2):
            source = fetch_run(st,req["id"])
            for attempt in source["attempts"]:
                resources.append({"stage":st,"id":req["id"],"arm":req["arm"],"block":req["block"],
                                  **{k:attempt[k] for k in ("attempt","started_utc","ended_utc","elapsed_s","status","usage")}})
        for cid in req["cases"]:
            case = cases[cid]
            obs = observations[(req["id"],cid)]
            pred = answers.get(cid)
            actual = [execute(case["family"],case["mode"],x) for x in case["heldout"]]
            valid = isinstance(pred,list) and len(pred)==4
            correct = [valid and type(x) == type(y) and x == y for x,y in zip(pred if valid else [None]*4,actual)]
            rows.append({**obs,"stable":case["stable"],"source_mode":case["source_mode"],"target_mode":case["mode"],
                         "heldout":case["heldout"],"expected":actual,"submitted":pred,"decision_status":status if valid else "invalid_or_missing",
                         "scored_utc":now(),"correct":correct,"perfect":all(correct),"n_correct":sum(correct)})
    dump("scores.json", rows)
    dump("resources.json", resources)
    counts = {}
    for arm in ARMS:
        own = [r for r in rows if r["arm"] == arm]
        usage = [r for r in resources if r["arm"] == arm]
        tokens = collections.Counter()
        for u in usage:
            tokens.update(u["usage"])
        counts[arm] = {"perfect":sum(r["perfect"] for r in own),"n_cases":len(own),"correct_outputs":sum(r["n_correct"] for r in own),
                       "n_outputs":4*len(own),"discriminating_actions":sum(r["separates_historical_alternatives"] for r in own),
                       "exact_discriminator_replays":sum(r["replayed_archived_discriminator"] for r in own),
                       "overlaps_heldout":sum(r["overlaps_heldout"] for r in own),
                       "executed_probes":sum(r["status"]=="executed" for r in own),
                       "stage2_valid":sum(r["decision_status"]=="ok" for r in own),
                       "attempts":len(usage),"usage":dict(tokens),"request_seconds_sum":round(sum(u["elapsed_s"] for u in usage),3)}
    by_family = summary_units(rows,"family")
    by_block = summary_units(rows,"block")
    supergroup = [{**r,"panel":(r["block"]-1)//2+1} for r in rows]
    panels = summary_units(supergroup,"panel")
    contrasts = {}
    for other in ("ordinary","fresh"):
        def differences(units):
            return {g:(v["discriminating"]-v[other])/v["cases_per_arm"] for g,v in units.items()}
        def jack(units):
            ds = list(differences(units).values())
            return [(sum(ds)-d)/(len(ds)-1) for d in ds]
        paired = collections.Counter()
        for cid in cases:
            duo = {r["arm"]:r["perfect"] for r in rows if r["case"] == cid}
            paired["win" if duo["discriminating"] > duo[other] else ("loss" if duo["discriminating"] < duo[other] else "tie")] += 1
        contrasts[other] = {"net_difference":(counts["discriminating"]["perfect"]-counts[other]["perfect"])/len(cases),
                            "paired":dict(paired),"family_differences":differences(by_family),"matched_batch_differences":differences(by_block),
                            "panel_differences":differences(panels),"leave_one_family_out_range":[min(jack(by_family)),max(jack(by_family))],
                            "leave_one_batch_out_range":[min(jack(by_block)),max(jack(by_block))]}
    dump("summary.json",{"scored_utc":now(),"counts":counts,"stable_or_reverted":summary_units(rows,"stable"),"families":by_family,
                        "matched_batches":by_block,"independent_family_panels":panels,"contrasts":contrasts})
    dump("failures.json",[r for r in rows if not r["perfect"] or r["status"]!="executed"])


if __name__ == "__main__":
    {"prepare":prepare,"freeze":freeze,"verify":verify,"observe":observe,"score":score}[sys.argv[1]]()

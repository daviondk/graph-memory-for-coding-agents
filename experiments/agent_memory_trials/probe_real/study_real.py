"""Commands prepare, freeze, verify, observe, score, audit. Standard library only."""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import zipfile

from fixtures import FAMILIES, accepted
from releases import PACKAGES

ROOT = Path(__file__).resolve().parent
SEED = 713548923


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(name):
    return json.loads((ROOT/name).read_text("utf-8"))


def dump(name, value):
    (ROOT/name).write_text(json.dumps(value,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")


def jsonl(name, values):
    (ROOT/name).write_text("".join(json.dumps(x)+"\n" for x in values),encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runwheel(project,version,inputs):
    if not all(accepted(project,x) for x in inputs):
        raise ValueError("input violates the adapter schema")
    spec = next(r for r in read("wheels.lock.json") if (r["project"],r["version"])==(project,version))
    wheel = ROOT/"wheels"/spec["filename"]
    assert sha(wheel)==spec["sha256"]
    start = now()
    with tempfile.TemporaryDirectory(prefix="wheel-contract-") as loc:
        target = Path(loc).resolve()
        with zipfile.ZipFile(wheel) as archive:
            assert all((target/m.filename).resolve().is_relative_to(target) for m in archive.infolist())
            archive.extractall(target)
        cmd = [sys.executable,"-I","-S","-B",str(ROOT/"adapter.py"),str(target)]
        proc = subprocess.run(cmd,cwd=target,input=json.dumps({"project":project,"inputs":inputs}),capture_output=True,text=True,encoding="utf-8",timeout=30,check=True)
    record = json.loads(proc.stdout)
    assert len(record["results"])==len(inputs)
    return {"project":project,"version":version,"wheel_sha256":spec["sha256"],"inputs":inputs,**record,"stderr":proc.stderr,
            "started_utc":start,"ended_utc":now(),"returncode":proc.returncode}


def setup_archives():
    records, cards = [],{}
    for p,versions in PACKAGES.items():
        inputs = FAMILIES[p]["history"]
        a,b = [runwheel(p,v,inputs) for v in versions[:2]]
        records.extend((a,b))
        ix = next(i for i in range(len(inputs)) if a["results"][i] != b["results"][i])
        cards[p] = {"input":inputs[ix],"observed":b["results"][ix]}
    return records,cards


INTRO = ("You maintain an application running a Python library on an unknown deployment snapshot. "
         "Its installed release is hidden. Your task is to predict results from its actual API. ")
ACT = ("Choose a single valid diagnostic input object now, aiming to distinguish plausible historical behaviors of this API. "
       "You may invent a probe or reuse any supplied old input. Only that one call will be executed for you. "
       "Return a JSON object with exactly one field probe holding your proposed input object.\n")
DEC = ("The only probe result on the target deployment is supplied below. Predict the wrapper result for each of the four pending "
       "inputs in order. Return a JSON object with exactly one field outputs holding an array of four strings.\n")


def prompt(row,cases,cards,obs=None):
    case = cases[row["case"]]
    rec = {"schema":FAMILIES[case["project"]]["manual"]}
    if row["arm"]=="archive":
        rec["one_archived_call_on_a_different_snapshot"] = cards[case["project"]]
    if obs is not None:
        rec["only_current_observation"] = obs
        rec["pending_application_inputs"] = case["tests"]
    return INTRO+(ACT if obs is None else DEC)+json.dumps(rec,sort_keys=True)


def prepare():
    assert not (ROOT/"freeze.json").exists()
    history,cards = setup_archives()
    dump("source_executions.json",history)
    dump("cards.json",cards)
    rng = random.Random(SEED)
    cases, plan = {},[]
    for p,versions in PACKAGES.items():
        tests = list(FAMILIES[p]["tests"])
        rng.shuffle(tests)
        for v,workload in zip(versions[2:],tests):
            k = f"R{rng.getrandbits(32):08X}"
            cases[k] = {"project":p,"version":v,"latest_historical_policy":v==versions[3],"tests":workload}
            for arm in ("archive","fresh"):
                plan.append({"case":k,"arm":arm})
    rng.shuffle(plan)
    for i,row in enumerate(plan):
        row["id"] = f"Q{i+1:02d}"
    dump("targets_hidden.json",cases)
    dump("allocation.json",plan)
    jsonl("stage1.jsonl",[{"id":r["id"],"prompt":prompt(r,cases,cards)} for r in plan])


def hashes():
    files = ["study_real.py","adapter.py","fixtures.py","releases.py","PROTOCOL.md","wheels.lock.json","source_executions.json",
             "cards.json","targets_hidden.json","allocation.json","stage1.jsonl","../shared/run_model.py"]
    files += ["wheels/"+r["filename"] for r in read("wheels.lock.json")]
    return {p:sha(ROOT/p) for p in files}


def freeze():
    assert not any((ROOT/x).exists() for x in ("freeze.json","runs1","runs2"))
    dump("freeze.json",{"utc":now(),"seed":SEED,"python":sys.version,"sha256":hashes()})


def verify():
    assert read("freeze.json")["sha256"]==hashes()


def model_result(stage,rid,key):
    run = read(f"runs{stage}/{rid}.json")
    if run["status"]!="ok":
        return None,run["status"]
    try:
        parsed = json.loads(run["text"])
        return parsed[key],"ok"
    except (ValueError,TypeError,KeyError):
        return None,"invalid_json_or_missing_field"


def observe():
    verify()
    cases,cards = read("targets_hidden.json"),read("cards.json")
    observations,requests = [],[]
    for row in read("allocation.json"):
        rid = row["id"]
        case = cases[row["case"]]
        proposed,status = model_result(1,rid,"probe")
        valid = accepted(case["project"],proposed) and status=="ok"
        executed = runwheel(case["project"],case["version"],[proposed]) if valid else None
        obs = {"input":proposed}
        if valid:
            obs["result"] = executed["results"][0]
        else:
            obs["error"] = "invalid or missing diagnostic input"
        observations.append({**row,"status":status,"valid":valid,"execution":executed,"observation":obs,"observed_utc":now()})
        requests.append({"id":rid,"prompt":prompt(row,cases,cards,obs)})
    dump("observations.json",observations)
    jsonl("stage2.jsonl",requests)


def score():
    verify()
    cases,cards = read("targets_hidden.json"),read("cards.json")
    obs = {r["id"]:r for r in read("observations.json")}
    results,checks = [],[]
    for row in read("allocation.json"):
        k = row["case"]
        case = cases[k]
        p, v = case["project"],case["version"]
        execution = runwheel(p,v,case["tests"])
        checks.append({"phase":"application_grading","id":row["id"],**execution})
        predictions,status = model_result(2,row["id"],"outputs")
        valid = isinstance(predictions,list) and len(predictions)==4 and all(type(x) is str for x in predictions)
        expected = execution["results"]
        bits = [a==b for a,b in zip(predictions,expected)] if valid else [False]*4
        ob = obs[row["id"]]
        prop = ob["observation"]["input"]
        separates = False
        if ob["valid"]:
            other = next(h for h in PACKAGES[p][2:] if h!=v)
            counter = runwheel(p,other,[prop])
            checks.append({"phase":"counterfactual_probe_scoring_after_decision","id":row["id"],**counter})
            separates = counter["results"][0] != ob["observation"]["result"]
        results.append({**row,**case,"probe_observation":ob["observation"],"probe_valid":ob["valid"],
                        "exact_replay":prop == cards[p]["input"],"probe_overlaps_test_input":prop in case["tests"],
                        "discriminating_probe":separates,"decision_transport":status,"decision_valid":valid,
                        "predictions":predictions,"expected":expected,"correct_bits":bits,"perfect":all(bits)})
    dump("scores.json",results)
    dump("grading_executions.json",checks)
    dump("failures.json",[r for r in results if not r["perfect"] or not r["probe_valid"]])
    resources = []
    for row in read("allocation.json"):
        for st in (1,2):
            run = read(f"runs{st}/{row['id']}.json")
            for att in run["attempts"]:
                resources.append({**row,"stage":st,**{k:att[k] for k in ("attempt","started_utc","ended_utc","status","elapsed_s","usage")}})
    dump("resources.json",resources)
    summary = {}
    for arm in ("archive","fresh"):
        rows = [r for r in results if r["arm"]==arm]
        items = [r for r in resources if r["arm"]==arm]
        tokens = collections.Counter()
        for i in items:
            tokens.update(i["usage"])
        summary[arm] = {"perfect":sum(r["perfect"] for r in rows),"n":len(rows),"correct_outputs":sum(sum(r["correct_bits"]) for r in rows),
                        "n_outputs":len(rows)*4,"executed_probes":sum(r["probe_valid"] for r in rows),
                        "informative_probes":sum(r["discriminating_probe"] for r in rows),"exact_replays":sum(r["exact_replay"] for r in rows),
                        "exact_input_overlap":sum(r["probe_overlaps_test_input"] for r in rows),
                        "latest_historical_policy_perfect":sum(r["perfect"] and r["latest_historical_policy"] for r in rows),
                        "earlier_policy_perfect":sum(r["perfect"] and not r["latest_historical_policy"] for r in rows),
                        "n_model_attempts":len(items),"usage":dict(tokens),"serial_request_seconds":round(sum(r["elapsed_s"] for r in items),3)}
    family = {}
    paired = collections.Counter()
    for p in PACKAGES:
        data = [r for r in results if r["project"]==p]
        family[p] = {a:sum(r["perfect"] for r in data if r["arm"]==a) for a in ("archive","fresh")}
        for k in {r["case"] for r in data}:
            pair = {r["arm"]:int(r["perfect"]) for r in data if r["case"]==k}
            paired[("loss","tie","win")[1+pair["archive"]-pair["fresh"]]] += 1
    diffs = [(r["archive"]-r["fresh"])/2 for r in family.values()]
    dump("summary.json",{"scored_utc":now(),"arms":summary,"by_package_out_of_two":family,"paired":dict(paired),
                         "perfect_rate_difference":sum(diffs)/3,"leave_one_package_out_differences":[(sum(diffs)-d)/2 for d in diffs]})


def audit():
    verify()
    frozen = read("freeze.json")
    allruns = read("resources.json")
    assert frozen["utc"] < min(r["started_utc"] for r in allruns)
    assert max(r["ended_utc"] for r in allruns if r["stage"]==1) < min(r["started_utc"] for r in allruns if r["stage"]==2)
    runs = read("scores.json")
    checks = read("grading_executions.json")
    assert len(runs)==12 and len({r["case"] for r in runs})==6
    for r in runs:
        src = read(f"runs1/{r['id']}.json")
        assert "pending_application_inputs" not in src["prompt"]
        assert ("one_archived_call_on_a_different_snapshot" in src["prompt"]) == (r["arm"]=="archive")
        tgt = json.loads(read(f"runs2/{r['id']}.json")["prompt"].split("\n")[-1])
        assert tgt["only_current_observation"] == r["probe_observation"] and tgt["pending_application_inputs"]==r["tests"]
        assert r["expected"] == next(c["results"] for c in checks if c["phase"]=="application_grading" and c["id"]==r["id"])
        assert r["expected"] == runwheel(r["project"],r["version"],r["tests"])["results"]
        assert len(set(PACKAGES[r["project"]]))==4
    print(json.dumps({"verified":True,"utc":now(),"first_started_utc":min(r["started_utc"] for r in allruns),
                      "last_ended_utc":max(r["ended_utc"] for r in allruns),"n_model_attempts":len(allruns),
                      "wheel_files":len(read("wheels.lock.json")),"cases":len(runs)//2,"arm_cases":len(runs)}))


if __name__=="__main__":
    {"prepare":prepare,"freeze":freeze,"verify":verify,"observe":observe,"score":score,"audit":audit}[sys.argv[1]]()

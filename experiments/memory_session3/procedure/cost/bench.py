"""Physical, paired measurements for two local tool backends on the sealed cache traces."""
import csv
import gzip
import hashlib
import json
import math
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from evaluate import dataset
from replay import Memory, effect, parse_read, split_cwd, tokens

SAVED = ROOT.parent / "predictions.jsonl.gz"
ORDER = ["bypass", "exact", "contained", "range"]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def run(docs, mode, collect=False):
    count, output, cost = 0, [], 0
    for doc in docs:
        bank = Memory(16,65536) if mode != "bypass" else None
        for i,group in enumerate(doc["groups"]):
            commands = [e["command"] for e in group]
            if bank is None:
                continue
            queries = [parse_read(c) for c in commands]
            effects = [effect(c) for c in commands]
            mixed = len(group) > 1 and any(kind != "read" for kind,names in effects)
            if not mixed:
                for j,(cmd,op) in enumerate(zip(commands,queries)):
                    if op is None:
                        continue
                    answer = bank.lookup(op,cmd,mode)
                    if answer is not None:
                        count += 1
                        if collect:
                            family = tokens(split_cwd(cmd)[1])[0]
                            output.append((doc["source"]["model"],doc["source"]["id"],i,j,op,answer,family))
            if mixed or any(kind == "unknown" for kind,names in effects) or any(e["result"] is None for e in group):
                bank.flush()
            else:
                paths = {p for _, names in effects for p in names}
                if paths:
                    bank.flush(paths)
            if mixed:
                continue
            for op,cmd,e in zip(queries,commands,group):
                if op is None:
                    continue
                r = e["result"]
                if r and r["rc"] == 0 and r["visible"]:
                    bank.write(op,cmd,r["text"])
                elif r and r["rc"] != 0:
                    bank.flush({op.path})
    return count,output

def expected():
    rows = {m: {} for m in ORDER[1:]}
    with gzip.open(SAVED,"rt",encoding="utf8") as f:
        for line in f:
            d = json.loads(line)
            key = (d["model"],d["id"],d["batch"],d["j"])
            for m in rows:
                h = d["pred"].get("main/"+m)
                if h is not None:
                    rows[m][key] = h
    return rows

def find_binary(family):
    pc = Path("C:/Program Files/Git/usr/bin") / (family+".exe")
    if pc.exists():
        return str(pc)
    name = shutil.which(family)
    if not name:
        raise RuntimeError("Missing GNU userland program " + family)
    return name

def fixture_args(case, path, binary):
    model,issue,i,j,op,ans,family = case
    if family == "cat":
        return [binary, str(path)]
    if family == "head":
        return [binary, "-n",str(op.hi),str(path)]
    end = "$" if op.hi is None else str(op.hi)
    return [binary,"-n",f"{op.lo},{end}p" if op.lo!=op.hi else f"{op.lo}p",str(path)]

def summarize(a):
    ordered = sorted(a)
    return {"mean":statistics.mean(a),"median":statistics.median(a),"p95":ordered[math.ceil(.95*len(a))-1],
            "min":min(a),"max":max(a)}

def main():
    docs = list(dataset())
    exp = expected()
    cases = []
    for mode in ORDER[1:]:
        _, observed = run(docs,mode,True)
        outputs = {r[:4]:sha(r[5].encode()) for r in observed}
        assert outputs == exp[mode]
        if mode == "range":
            cases = observed
    rng = random.Random(17112026)
    maint = []
    for block in range(5):
        order = ORDER.copy()
        rng.shuffle(order)
        for m in order:
            st = time.perf_counter_ns()
            count,_ = run(docs,m)
            elapsed = (time.perf_counter_ns()-st)/1e6
            assert count == len(exp.get(m,{}))
            maint.append({"block":block,"policy":m,"ms":elapsed,"count":count})
    binaries = {r[6]:find_binary(r[6]) for r in cases}
    versions = {k: subprocess.check_output([b,"--version"]).splitlines()[0].decode() for k,b in binaries.items()}
    times = []
    with tempfile.TemporaryDirectory(prefix="fixtures_",dir=ROOT) as td:
        entries = []
        for k,case in enumerate(cases):
            *_,op,ans,family = case
            path = Path(td) / (str(k)+".txt")
            content = ans.encode()
            path.write_bytes(b"\n"*(op.lo-1) + content)
            entries.append((fixture_args(case,path,binaries[family]),path,op,content))
        for b in range(2):
            order = list(range(len(cases)))
            rng.shuffle(order)
            for k in order:
                args, path,op,content = entries[k]
                methods = ["process","python"]
                rng.shuffle(methods)
                for name in methods:
                    st = time.perf_counter_ns()
                    if name == "process":
                        res = subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                        out, rc = res.stdout,res.returncode
                    else:
                        with path.open("rb") as f:
                            out,rc = b"".join(f.readlines()[op.lo-1:op.hi]),0
                    elapsed = (time.perf_counter_ns()-st)/1e6
                    assert rc == 0 and out == content,(cases[k][:4],args,rc,sha(out),sha(content))
                    key = cases[k][:4]
                    times.append({"block":b,"model":key[0],"issue":key[1],"group":key[2],"event":key[3],
                                  "backend":name,"ms":elapsed,"also_contained":int(key in exp["contained"]),
                                  "also_exact":int(key in exp["exact"])})
    for file, rows in (("management.csv",maint),("physical.csv",times)):
        with (ROOT/file).open("w",encoding="utf8",newline="") as f:
            w = csv.DictWriter(f,fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    mm = {(r["block"],r["policy"]):r["ms"] for r in maint}
    contrasts = {}
    for mode,base in (("range","bypass"),("contained","bypass"),("exact","bypass"),("range","contained")):
        diff = [mm[b,mode]-mm[b,base] for b in range(5)]
        gain = len(exp[mode])-len(exp.get(base,{}))
        contrasts[mode+"-"+base] = {"hits":gain,"incremental_ms":summarize(diff),
                                    "break_even_ms_per_skipped_call":summarize([d/gain for d in diff])}
    physical = {m:summarize([r["ms"] for r in times if r["backend"]==m]) for m in ["process","python"]}
    for m in physical:
        for name,delta in contrasts.items():
            mode,base = name.split("-")
            obs = []
            for b in range(2):
                use = [r for r in times if r["block"]==b and r["backend"]==m and
                       (mode=="range" or r["also_"+mode]) and (base=="bypass" or not r["also_"+base])]
                assert len(use)==delta["hits"]
                obs.append(sum(r["ms"] for r in use))
            delta[m+"_avoided_ms_by_block"] = obs
            delta[m+"_net_ms_vs_median_management"] = [v-delta["incremental_ms"]["median"] for v in obs]
    results = {"host":platform.platform(),"python":sys.version,"userland":versions,"cpu":platform.processor(),
               "branches":dict(Counter(r[6] for r in cases)),"lock_sha256":sha(SAVED.read_bytes()),
               "protocol_sha256":sha((ROOT/"PROTOCOL.md").read_bytes()),
               "benchmark_sha256":sha(Path(__file__).read_bytes()),"timing_hashes":{n:sha((ROOT/n).read_bytes()) for n in ["management.csv","physical.csv"]},
               "management":contrasts,"physical_ms_per_call":physical,"verified_physical_outputs":len(times)}
    (ROOT/"results.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf8")
    print(json.dumps(results,indent=1))

if __name__ == "__main__":
    main()


"""Portable consistency checks of held-out cohort, initial tests, reruns and paired outcomes."""
from collections import defaultdict
from pathlib import Path
import gzip
import json
import hashlib
import sys

ROOT=Path(__file__).resolve().parent


def load(n):
    data=(ROOT/n).read_bytes()
    return json.loads(gzip.decompress(data) if n.endswith(".gz") else data)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    return {p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}


def check():
    m=manifest()
    assert m==load("MANIFEST_SHA256.json")
    plan=load("design-lock.json");seal=load("forecast-seal.json");obs=load("observation-lock.json")
    for n in ["study.py","local_run.py"]:
        assert plan["inputs"][n]==m[n]
    assert plan["inputs"]["protocol"]==m["PROTOCOL_RU.md"]
    assert obs["design"]==seal["design"]==m["design-lock.json"] and seal["observation"]==m["observation-lock.json"]
    assert seal["forecast"]==m["forecasts.json.gz"] and load("stream-index.json")["seal"]==m["forecast-seal.json"]
    hashes=lambda s:hashlib.sha256(s.encode()).hexdigest()
    assert sorted(plan["roster"])==sorted(sorted(plan["eligible"],key=lambda n:hashes("R20 code transfer target|"+n))[:18])
    assert not set(plan["roster"])&set(plan["excluded_prior"])
    records=load("native-receipts.json.gz")
    initial={(r["name"],r["state"]):r for r in records["initial"]}
    checks={(r["name"],r["state"],r["node"]):r for r in records["reruns"]}
    assert len(initial)==len(records["initial"]) and len(checks)==len(records["reruns"])
    f={(r["target"],r["state"]):r for r in load("forecasts.json.gz")}
    o={(r["target"],r["state"]):r for r in load("outcomes.json.gz")}
    assert set(f)==set(o)=={(name,variant) for name in plan["roster"] for variant in ("correct","buggy")}
    aggregated=defaultdict(int)
    for (name,state),r in o.items():
        others=sorted(set(plan["eligible"])-{name},key=lambda n:hashes("R20 context|"+name+"|"+n))[:12]
        assert plan["roster"][name]==sorted(others+[name],key=lambda n:hashes("R20 order|"+name+"|"+n))
        rr=[initial[n,state if n==name else "correct"] for n in plan["roster"][name]]
        common={node:(x["name"],x["state"]) for x in rr for node in x["collect"]}
        fail=set(n for x in rr for n in x["fail"])
        unknown=not all(x["known"] for x in rr)
        assert unknown==r["unknown"] and fail==set(r["gold"])
        for arm,v in r["actions"].items():
            pred=f[name,state]["arms"][arm]
            node=pred["selected"];assert node==v["node"] and v["valid"]==(node in common)
            if "picked" in pred:
                assert set(pred["picked"])<=set(pred["kept"]) and pred["read"]<=2048
                if arm!="full_history":assert pred["stored"]<=8192
            rerun=checks.get((*common[node],node)) if node in common else None
            confirmed=bool(rerun and rerun["known"] and rerun["fail"]==[node] and rerun["collect"]==[node])
            ok=not unknown and ((node is None and not fail) or (node in fail and confirmed))
            assert confirmed==v["confirmed"] and ok==v["success"]
            aggregated[arm]+=int(ok)
    res=load("results.json")
    assert all(res["stats"][arm]["success"]==num for arm,num in aggregated.items())
    assert all(r["raw_tokens"]>8192 for r in f.values())
    print("OK:",len(m),"files,",len(o),"episodes,",len(initial),"initial native suites,",len(checks),"native single-test repeats")


if __name__=="__main__":
    if "--write-manifest" in sys.argv:
        (ROOT/"MANIFEST_SHA256.json").write_bytes((json.dumps(manifest(),sort_keys=True,indent=2)+"\n").encode())
    check()

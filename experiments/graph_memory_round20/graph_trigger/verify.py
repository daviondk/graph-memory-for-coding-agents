"""No dependency on benchmark code, a model, CPU vector library or GPU."""
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import math
import sys

ROOT=Path(__file__).resolve().parent
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):
    raw=(ROOT/n).read_bytes()
    return json.loads(gzip.decompress(raw) if n.endswith(".gz") else raw)
def s(t):return hashlib.sha256(t.encode()).hexdigest()
def files():return {p.name:h(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}


def main():
    m=files()
    if "--write-manifest" in sys.argv:
        (ROOT/"MANIFEST_SHA256.json").write_bytes((json.dumps(m,indent=2,sort_keys=True)+"\n").encode())
    assert read("MANIFEST_SHA256.json")==m
    plan=read("plan.json");assert plan["protocol"]==m["PROTOCOL_RU.md"] and plan["code"]==m["gate.py"]
    seal=read("feature-seal.json");assert all(m[n]==z for n,z in seal["files"].items())
    train=read("dev-features.json.gz");test=read("test-features.json.gz");qual=[p.name[:-13] for p in ROOT.glob("*-results.json")]
    assert len(train)==500 and len(test)==2000 and len({r["t"] for r in test})==1207
    assert all(not {r[k] for r in train}&{r[k] for r in test} for k in ["q","t"])
    if not qual and "--features-only" in sys.argv:
        print("Verified the pre-outcome feature package: 500 dev and 2000 test queries")
        return
    assert qual,"no graph panel"
    for tag in qual:
        fit=read(tag+"-model.json");dec={r["q"]:r for r in read(tag+"-decisions.json.gz")}
        ds=read(tag+"-decision-seal.json");assert ds["model"]==m[tag+"-model.json"] and ds["decisions"]==m[tag+"-decisions.json.gz"]
        result=read(tag+"-results.json");outs=read(tag+"-outcomes.json.gz");assert result["decision"]==m[tag+"-decision-seal.json"]
        for r in test:
            q=r["q"];d=dec[q];assert r["t"]==d["t"]
            y=sum((v-mu)/sd*c for v,mu,sd,c in zip(r["z"],fit["means"],fit["scale"],fit["coef"]))+fit["intercept"]
            assert math.isclose(y,d["s"]["gate"],rel_tol=1e-11,abs_tol=1e-12)
            assert d["s"]["margin"]==-r["z"][4]
            for arm in ["gate","margin"]:
                for k in [25,50,75]:
                    score,key=fit["cutoffs"][arm][str(k)]
                    assert d["call"][arm+str(k)]==((-d["s"][arm],s("R20 gate tie|"+arm+"|"+q))<=(-score,key))
        for k in [25,50,75]:
            calls=sum(z["call"]["gate"+str(k)] for z in dec.values())
            randoms=sorted(dec,key=lambda q:s("R20 matched random calls|"+q))[:calls]
            assert {q for q in dec if dec[q]["call"]["random"+str(k)]}==set(randoms)
        assert len(outs)==len(dec)==2000 and {r["q"] for r in outs}==set(dec)
        for r in outs:
            assert all(r["methods"][arm]==("graph" if flag else "dense") for arm,flag in dec[r["q"]]["call"].items())
        for a,v in result["stats"].items():
            assert v["calls"]==sum(r["methods"][a]=="graph" for r in outs)
            assert v["fs"]==sum(r[r["methods"][a]]["fs"] for r in outs)
        primary=result["primary"];assert primary["met"]==(primary["rate"]<=.60 and primary["lower"]>-.01)
        assert primary["lower"]==result["paired"]["gate50-always_graph"]["metric"]["fs"]["ci"][0]
        if (ROOT/(tag+"-runtime.json")).exists():
            rt=read(tag+"-runtime.json")
            assert rt["code_sha"]==m["runtime_probe.py"] and rt["protocol_sha"]==m["RUNTIME_RU.md"]
            assert rt["decision_sha"]==m[tag+"-decisions.json.gz"]
            ids=sorted(dec,key=lambda q:s("R20 gate runtime v1|"+q))[:96]
            assert ids==rt["q"] and rt["n"]==96 and rt["cpu_threads"]==1
            for pair in rt["pairs"]:
                assert pair["always"]["calls"]==96
                assert pair["gate"]["calls"]==sum(dec[q]["call"]["gate50"] for q in ids)
                assert math.isclose(pair["ratio_gate_to_always"],pair["gate"]["seconds"]/pair["always"]["seconds"])
        if (ROOT/(tag+"-source-transfer.json")).exists():
            chk=read(tag+"-source-transfer.json"); seen=read("transfer-source-flags.json.gz")
            assert chk["outcomes"]==m[tag+"-outcomes.json.gz"] and chk["flags"]==m["transfer-source-flags.json.gz"]
            assert {r["q"] for r in seen}==set(dec) and len(seen)==len(outs)
            trust={r["q"]:r for r in seen}
            for spec,v in chk["panels"].items():
                keep=[r for r in outs if not trust[r["q"]]["gate_dev"] and
                      (spec=="omit_dev_matches" or not trust[r["q"]]["dense_train"])]
                assert len(keep)==v["n"] and sum(r["methods"]["gate50"]=="graph" for r in keep)==v["calls"]
                assert sum(r["graph"]["fs"] for r in keep)==v["graph"]
                assert sum(r[r["methods"]["gate50"]]["fs"] for r in keep)==v["gate"]
                assert v["criterion"]==(v["paired_fs"]["ci"][0]>-.01 and v["calls"]/v["n"]<=.60)
        print(tag,len(outs),"out-of-split routing decisions and all marginal totals verified")

if __name__=="__main__":main()

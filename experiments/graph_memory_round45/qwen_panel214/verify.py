"""Offline SHA validation, panel disjointness, ranking checks and aggregate reconstruction."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import sys

D=Path(__file__).resolve().parent


def get(name):
    p=D/name
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)


def sha(name):
    with (D/name).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def verify(final):
    panel=get("panel.json")
    ids=set(panel["order"]);pilot=set(panel["pilot"]);remaining=set(panel["remaining"])
    assert ids==pilot|remaining and not pilot&remaining and (len(ids),len(pilot),len(remaining))==(214,10,204)
    assert len(panel["order"])==214 and panel["order"]==panel["pilot"]+panel["remaining"]
    assert len(set(panel["repo"].values()))==69 and sum(panel["candidates"].values())==18598
    assert sha("PROTOCOL_RU.md")==panel["protocol"]
    controls=get("controls-seal.json")
    assert sha("control-ranks.json.gz")==controls["forecasts"] and sha("controls.py")==controls["program"]
    cr=get("control-ranks.json.gz")
    assert cr.keys()==ids and all(len(set(seq))==len(seq)==8 for r in cr.values() for seq in r.values())
    if final:
        gpu=get("gpu-seal.json")
        qwen=get("qwen-scores.json.gz")
        assert sha("qwen-scores.json.gz")==gpu["forecasts"] and len(gpu["backend"])>0 and qwen.keys()==ids
        ranks=get("predictions.json.gz")
        outcomes=get("outcomes.json.gz")
        res=get("results.json")
        assert sha("gpu-seal.json")==res["gpu_seal"] and sha("controls-seal.json")==res["controls"] and sha("outcomes.json.gz")==res["outcomes"]
        for q in ids:
            v=qwen[q];s=v["scores"]
            assert len(s)==panel["candidates"][q] and all(math.isfinite(x) for x in s.values())
            assert len(v["lengths"])==len(s)+1 and sum(min(n,512) for n in v["lengths"])==v["tokens"]
            assert sorted(s,key=lambda k:(-s[k],k))[:8]==v["ranks"]["qwen"]
            assert ranks[q]==cr[q]|v["ranks"] and outcomes[q]["repo"]==panel["repo"][q]
        for name,subset in (("all214",ids),("outside204",remaining),("pilot10",pilot)):
            tab=res["panels"][name]
            assert tab["states"]==len(subset) and tab["repos"]==len({panel["repo"][q] for q in subset})
            for method,r in tab["methods"].items():
                assert r["complete_counts"]==[sum(outcomes[q]["arms"][method][j] for q in subset) for j in range(4)]
        if (D/"manifest.json").exists():
            for p,digest in get("manifest.json")["files"].items():assert sha(p)==digest,p
    print("Verified",len(ids),"states,",len(pilot),"pilot,",len(remaining),"outside pilot,",len(set(panel['repo'].values())),"repos.","Final outputs checked." if final else "Preflight only.")


if __name__=="__main__":
    verify("--final" in sys.argv)

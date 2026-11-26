"""Audit the released finite panel without the archive's execution environment."""
import gzip,hashlib,json
from collections import Counter
from pathlib import Path
D=Path(__file__).resolve().parent
def read(name):
    p=D/name;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(name):return hashlib.sha256((D/name).read_bytes()).hexdigest()
def verify():
    r=read("results.json");sup=read("support-results.json");seal=read("seal.json");ss=read("support-seal.json")
    assert seal["result"]==r["predictions"]==sha("predictions.json.gz")
    assert seal["protocol"]==sha("PROTOCOL_RU.md") and seal["code"]==sha("predict.py")
    assert ss["dist"]==sha("support-distance.json.gz") and ss["code"]==sha("support.py") and ss["protocol"]==sha("PROTOCOL_SUPPORT_RU.md")
    assert r["score"]==sha("scored.json.gz") and sup["scored"]==sha("support-scored.json.gz")
    p=read("predictions.json.gz");ds=read("support-distance.json.gz");obs=read("scored.json.gz");ssr=read("support-scored.json.gz")
    assert len(p)==len(obs)==len(ssr)==1282 and set(p)==set(ds)=={z["q"] for z in obs}=={z["q"] for z in ssr}
    for q,v in p.items():
        old={n:(h,s) for n,h,s in v["old"]};receipt=dict(v["receipt"])
        assert set(old).isdisjoint(receipt) and len(old)+len(receipt)<=128
        for n,(h,s) in old.items():
            agreeing=[abs(n-i) for i,match in v["witness"][s] if match]
            assert ds[q][str(n)]==min(agreeing,default=None)
            mismatch=[abs(n-i) for i,match in v["witness"][s] if not match]
            assert (n in v["drop"]["side"])==bool(mismatch)
            expected=bool(mismatch) and min(mismatch)<=8 and min(mismatch)<min(agreeing,default=float("inf"))
            assert (n in v["drop"]["local"])==expected
    total=Counter()
    for v in obs:
        total.update(v["stats"])
        assert v["stats"]["wrong"]==v["stats"]["wrong_receipt"]+v["stats"]["wrong_carried"]
    assert total["wrong"]==83 and total["wrong_carried"]==63 and total["alerted_carried_wrong"]==0
    assert total["mismatches"]==total["any_conflict"]==1 and total["overlaps"]==2151
    assert sum(v["stats"]["wrong"] for v in obs if v["barrier_after"])==71
    assert all(v["arms"]["side"][1]==v["arms"]["side"][4] for v in ssr)
    assert sum(v["arms"]["side"][0] for v in ssr)==693 and sum(v["arms"]["side"][1] for v in ssr)==56
    for name,g in r["groups"].items():
        assert g["counts"]["wrong"]==sum(v["stats"]["wrong"] for v in obs if v["zone"]==name)
    print("verified 1282 forecasts, both geometry gates, coverage diagnostics and counterfactual controls")
if __name__=="__main__":verify()


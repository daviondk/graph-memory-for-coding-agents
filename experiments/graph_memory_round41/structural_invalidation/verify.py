"""Offline verification of forecast bindings, the SQL subset and reported contrasts."""
from collections import defaultdict
import gzip,hashlib,json
from pathlib import Path

D=Path(__file__).resolve().parent

def load(n):
    x=(D/n).read_bytes()
    return json.loads(gzip.decompress(x) if n.endswith(".gz") else x)

def sha(n):return hashlib.sha256((D/n).read_bytes()).hexdigest()

def main():
    p=load("predictions.json.gz");a=load("audit.json.gz");s=load("forecast-seal.json");z=load("results.json")
    assert set(p)==set(a) and len(p)==2696 and sum(v["held"] for v in a.values())==1071
    assert sha("predictions.json.gz")==s["results"] and sha("audit.json.gz")==load("audit-seal.json")["sha"]
    for f,k in s["program"].items():assert sha(f)==k
    assert sha("audit-seal.json")==z["audit"]
    for panel,ids in (("all2696",list(p)),("held1071",[k for k,v in a.items() if v["held"]]),
                       ("main676",[k for k,v in a.items() if v["group"]=="main"])):
        rr=z["panels"][panel];assert rr["events"]==len(ids)
        for method,t in rr["methods"].items():
            assert t["whole_same"]==sum(p[k]["old"]==p[k]["choices"][method] for k in ids)
            assert t["strict"]==sum((p[k]["old"]==p[k]["choices"][method] and
                                not a[k]["metrics"][method].get("selected_bad_after",0)) for k in ids)
            assert t.get("bad_new",0)==sum(a[k]["metrics"][method].get("bad_new",0) for k in ids)
        for pair,c in rr["paired"].items():
            m,n=pair.split("_minus_");unit=defaultdict(list)
            for k in ids:unit[p[k]["issue"]].append(a[k]["metrics"][m]["strict"]-a[k]["metrics"][n]["strict"])
            assert abs(sum(sum(u)/len(u) for u in unit.values())/len(unit)-c["macro"])<1e-10
    extra=load("sql-input.json.gz");native=load("native-sql.json")
    assert sha("sql-input.json.gz")==load("sql-input-seal.json")["file"]==native["source"]
    assert sha("sql.py")==native["code"] and set(extra)==set(native["rows"]) and len(extra)==64
    for k,rr in extra.items():
        out=native["rows"][k]
        if out is None:assert not rr["blocks"] and not rr["expected"];continue
        assert out["closed_slots"]==rr["expected"] and out["edge_count"]==len(rr["expected"])
        assert out["blocks"]==len(rr["blocks"])
    if (D/"manifest.json").exists():
        for n,d in load("manifest.json")["files"].items():assert sha(n)==d,n
    print("Verified 2696 rankings and byte audits, 1071 held-out events, 64 native symbol projections, and all primary contrasts.")

if __name__=="__main__":main()


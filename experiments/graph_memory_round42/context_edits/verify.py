"""Offline verification of inputs, typed alignment, intervals and raw aggregate rates."""
from collections import defaultdict
import gzip,hashlib,json
from pathlib import Path
from mechanism import match

D=Path(__file__).resolve().parent


def read(n):
    b=(D/n).read_bytes();return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)


def sha(n):return hashlib.sha256((D/n).read_bytes()).hexdigest()


def main():
    a=read("action-lines.json.gz");p=read("predictions.json.gz");out=read("audit.json.gz");r=read("results.json")
    assert set(a)==set(p)==set(out) and len(p)==2696
    assert read("action-seal.json")["actions"]==sha("action-lines.json.gz")
    f=read("forecast-seal.json")
    assert f["predictions"]==sha("predictions.json.gz") and f["actions"]==sha("action-seal.json")
    for n,d in f["code"].items():assert sha(n)==d
    assert read("audit-seal.json")["predicted"]==sha("forecast-seal.json") and sha("audit.json.gz")==read("audit-seal.json")["audit"]
    assert sha("audit-seal.json")==r["audit"] and sha("exhaustive.json")==r["exhaustive"]
    assert not read("exhaustive.json")["counts"]["wrong"]
    t=read("timing-seal.json")
    assert t["rows"]==sha("timing.json.gz") and len(read("timing.json.gz"))==len(p)
    for k,z in p.items():
        edges,complete,detail=match(a[k]["old"],a[k]["new"])
        assert edges.items()<=complete.items() and detail==z["stats"]
        assert z["positions"]["edges"].items()<=z["positions"]["local"].items()
        for m in ("local","edges"):
            assert int(z["choices"][m]==z["old"])==out[k]["metrics"][m]["whole_same"]
    for n,ids in (("held1071",[k for k,v in p.items() if v["held"]]),("all2696",list(p)),("main676",[k for k,v in p.items() if v["group"]=="main"])):
        data=r["panels"][n]
        assert data["events"]==len(ids) and data["issues"]==len({p[k]["issue"] for k in ids})
        for m,tab in data["methods"].items():
            for metric in ("strict","whole_same","mapped_bytes","bad_new"):
                assert tab.get(metric,0)==sum(out[k]["metrics"][m].get(metric,0) for k in ids)
        for pair,c in data["paired"].items():
            a1,b1=pair.split("_minus_")
            unit=defaultdict(list)
            for k in ids:unit[p[k]["issue"]].append(out[k]["metrics"][a1]["strict"]-out[k]["metrics"][b1]["strict"])
            assert abs(c["macro"]-sum(sum(x)/len(x) for x in unit.values())/len(unit))<1e-10
    if (D/"manifest.json").exists():
        for n,d in read("manifest.json")["files"].items():assert sha(n)==d,n
    print("Verified 2696 ranks, visible action alignments, byte audits, four score panels and the cluster-level primary contrast.")


if __name__=="__main__":main()


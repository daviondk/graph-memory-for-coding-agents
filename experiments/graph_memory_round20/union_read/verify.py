"""Portable verification from hashed source coordinates, independent of the GPU."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parent


def sha(f):
    return hashlib.sha256(f.read_bytes()).hexdigest()


def load(f):
    b=(ROOT/f).read_bytes()
    return json.loads(gzip.decompress(b) if f.endswith(".gz") else b)


def manifest():
    return {p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!="MANIFEST_SHA256.json"}


def coordinates(arr):
    groups=defaultdict(list)
    for e,p,a,b,c in arr:
        assert 0<=a<b and c>0
        groups[e,p].append((a,b))
    out={}
    for key,pairs in groups.items():
        seq=[]
        for a,b in sorted(pairs):
            if seq and a<=seq[-1][1]:
                seq[-1]=(seq[-1][0],max(seq[-1][1],b))
            else:seq.append((a,b))
        out[key]=seq
    return out


def nested(a,b):
    return all(any(i<=left and right<=j for i,j in b.get(key,[])) for key,ranges in a.items() for left,right in ranges)


def verify(model):
    dig=manifest()
    assert load("design-lock.json")["code"]==dig["pack.py"]
    assert load("design-lock.json")["protocol"]==dig["PROTOCOL_RU.md"]
    assert load(model+"-plan.json")["design"]==dig["design-lock.json"]
    assert load(model+"-duplicate-plan.json")["protocol"]==dig["OVERLAP_CONTROL_RU.md"]
    assert load("strict-plan.json")["code"]==dig["strict_render.py"]
    o={r["q"]:r for r in load(model+"-outcomes.json.gz")}
    so={r["q"]:r for r in load(model+"-strict-outcomes.json.gz")}
    assert len(o)==len(so)==2000 and set(o)==set(so)
    assert len({r["t"] for r in o.values()})==1207
    for variant in ("forecast","duplicate","strict"):
        seal=load(model+"-"+variant+"-seal.json")
        assert all(x["sha"]==dig[x["file"]] for x in seal["shards"])
    stats=load(model+"-results.json");strict=load(model+"-strict-results.json")
    clean=load(model+"-clean-sensitivity.json")
    assert clean["strict_outcomes_sha256"]==dig[model+"-strict-outcomes.json.gz"]
    parts=clean["partitions"];assert sorted(v["n"] for v in parts.values())==[125,1875]
    for arm in ("F","skip"):
        assert sum(v["full_support_counts"][arm] for v in parts.values())==strict["stats"][arm]["fs"]
    audit=load(model+"-render-audit.json")
    assert audit["strict_forecasts_sha256"]==dig[model+"-strict-seal.json"] and audit["literal_documents"]==12000
    got=set();six=("F","F0","W","W0","U","skip")
    strict_non_nested=Counter()
    for i in range(8):
        frozen=load(f"{model}-pred-{i}.json.gz")
        duo={r["q"]:r for r in load(f"{model}-dup-{i}.json.gz")};tr={r["q"]:r for r in load(f"{model}-strict-{i}.json.gz")}
        for qrow in frozen:
            q=qrow["q"];assert q not in got;got.add(q)
            assert o[q]["t"]==so[q]["t"]==qrow["t"]==duo[q]["t"]==tr[q]["t"]
            for batch,score,restricted in [({**qrow["arms"],**duo[q]["arms"]},o,False),(tr[q]["a"],so,True)]:
                sc={k:coordinates(batch[k]) for k in six}
                for a,b in (("skip","U"),("U","W"),("W","F"),("skip","W0"),("W0","F0"),("skip","F")):
                    inc=nested(sc[a],sc[b])
                    if restricted:strict_non_nested[a+"-in-"+b]+=int(not inc)
                    else:assert inc
                for arm in six:
                    v=score[q]["a"][arm]
                    total=sum(c for *_,c in batch[arm]);assert total<=2048 and total==v["tokens"]
                    assert sum(right-left for iv in sc[arm].values() for left,right in iv)==v["chars"]
                    assert len(sc[arm])==v["events"]
                    if restricted:assert total==tr[q]["info"][arm]["new_cost"]
    assert dict(strict_non_nested)==strict["inclusion_violations"]
    for arm in six:
        assert sum(r["a"][arm]["full_support"] for r in o.values())==stats["stats"][arm]["count"]
        assert sum(r["a"][arm]["full_support"] for r in so.values())==strict["stats"][arm]["fs"]
        assert sum(r["a"][arm]["tokens"] for r in so.values())==audit["by_arm"][arm]["tok"]
    for out,prior in [(o,stats),(so,strict)]:
        for contrast,record in prior["paired"].items():
            a,b=contrast.split("-");changes=[r["a"][a]["full_support"]-r["a"][b]["full_support"] for r in out.values()]
            assert record["win"]==changes.count(1.) and record["lose"]==changes.count(-1.)
            assert abs(mean(changes)-record["change"]["full_support"]["mean"])<1e-12
    print(model,len(got),"questions; both 12,000-cell panels, literal-render hashes and means verified")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--write-manifest",action="store_true")
    p.add_argument("--require-both",action="store_true")
    args=p.parse_args()
    if args.write_manifest:(ROOT/"MANIFEST_SHA256.json").write_bytes((json.dumps(manifest(),sort_keys=True,indent=2)+"\n").encode())
    assert load("MANIFEST_SHA256.json")==manifest()
    panels=[k for k in ["dense","hash64","availability","rgcn"] if (ROOT/f"{k}-render-audit.json").exists()]
    assert "dense" in panels and (not args.require_both or len(panels)>=2)
    for k in panels:verify(k)

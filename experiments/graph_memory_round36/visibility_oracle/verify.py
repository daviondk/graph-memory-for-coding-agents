"""Validate counts and receipts without the private data or graph runtime."""
import argparse,json,gzip,hashlib
from pathlib import Path
from collections import Counter
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def main():
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");a=p.parse_args()
    plan=read(D/"plan.json");r=read(D/"results.json");cross=read(D/"cross-check.json");al=read(D/"call-alignment.json")
    data=read(D/"histories.json.gz");assert len(data)==1207 and r["units"]==al["input"]==cross["independent_source"]==sha(D/"histories.json.gz")
    assert r["plan"]==sha(D/"plan.json") and plan["protocol"]==sha(D/"PROTOCOL_RU.md") and plan["code"]==sha(D/"study.py")
    assert cross["code"]==sha(D/"cross.py") and cross["endpoint_audit"]==sha(D/"call-alignment.json") and al["code"]==sha(D/"align.py")
    assert cross["equalities"]==38624 and len(al["adjustments"])==2
    assert set(plan["native_sample"])==set(r["native_prefixes"]) and len(plan["native_sample"])==16 and sum(r["native_prefixes"].values())==434
    assert len(r["synthetic"])==4
    for cut,m in r["sums"].items():
        for unit in ("call_pairs","pu_pairs"):
            sums=Counter()
            for history in data.values():sums.update(history[cut][unit])
            assert sums==m[unit] and sums["E"]<=sums["M"]<=sums["L"]
            assert sums["L"]-sums["M"]==sums["equal_boundary"]+sums["before_boundary"]
    target=D/"manifest.json";manifest={p.name:sha(p) for p in D.iterdir() if p.is_file() and p!=target}
    if a.seal and not target.exists():target.write_text(json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8",newline="\n")
    assert manifest==read(target)
    print("Verified 4,828 states, 434 native checks and four atomic-event fixtures.",sha(target))
if __name__=="__main__":main()

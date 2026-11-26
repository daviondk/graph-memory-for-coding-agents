from pathlib import Path
import gzip,hashlib,json
from collections import defaultdict
D=Path(__file__).resolve().parent
load=lambda p:json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
sc=load(D/"scoring.json");sealed=load(D/"forecast-seal.json")
assert len(sealed["packets"])==40
rows=[]
for key,dig in sealed["packets"].items():
    assert hashlib.sha256((D/(key+".json.gz")).read_bytes()).hexdigest()==dig
for k,dig in sc["scores"].items():
    p=D/f"outcomes-{k}.json.gz";assert hashlib.sha256(p.read_bytes()).hexdigest()==dig
    rows.extend(load(p))
assert len({(r["q"],r["cut"]) for r in rows})==len(rows)==8000
s=load(D/"results.json")
selected=[r for r in rows if r["cut"]==50 and not r["pilot"] and r["eligible"]]
assert len(selected)==901 and len({r["t"] for r in selected})==657
primary=s["groups"]["50/eligible"]
for arm in primary["means"]:
    total=sum(v[arm][0] for r in selected for v in r["arms"].values())
    assert total==round(primary["means"][arm][0]*4505)
for seed in s["seeds"]:
    assert sum(load(D/f"pred-{seed}-{j}-seal.json")["terminal"] for j in range(8))==2000
print("Verified 40000 forecast states and 10000 complete-history checks",sc["official_unique_lists"])


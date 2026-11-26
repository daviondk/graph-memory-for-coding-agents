import hashlib,json,gzip
from pathlib import Path
D=Path(__file__).resolve().parent
def load(p):
 b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=load(D/"manifest.json")
for f,h in manifest.items():assert sha(D/f)==h,f
s=load(D/"selection.json");r=load(D/"results.json");seal=load(D/"test-seal.json")
assert seal["chosen"]==sha(D/"selection.json") and all(sha(D/f)==h for f,h in seal["files"].items())
assert s["dev"]==sha(D/"dev-results.json") and r["outcomes"]==sha(D/"test-outcomes.json.gz")
a=s["chosen"]["slack"];b=s["chosen"]["control"];rows=load(D/"test-outcomes.json.gz")
assert len(rows)==2000 and len({v["t"] for v in rows.values()})==1207
d=sum(sum(x[a][0]-x[b][0] for x in v["seeds"].values()) for v in rows.values())/(2000*5)
assert abs(d-r["data"]["all5"]["vs"][b]["FS2048"]["delta"])<1e-12
print(f"Verified {len(manifest)} files, 10,000 question-seed pairs, primary delta {100*d:.2f} percentage points.")
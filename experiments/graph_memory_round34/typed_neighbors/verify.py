import hashlib,json,gzip
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):
 b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(D/"manifest.json")
for f,h in manifest.items():assert sha(D/f)==h,f
for k in ("dev","test"):
 assert read(D/(k+"-seal.json"))["ranks"]==sha(D/(k+"-ranks.json.gz"))
 assert read(D/(k+"-results.json"))["outcomes"]==sha(D/(k+"-outcomes.json.gz"))
sel=read(D/"selection.json");assert read(D/"test-seal.json")["chosen"]==sha(D/"selection.json")
rows=read(D/"test-outcomes.json.gz");vals=[r["arms"][sel["treatment"]][0]-r["arms"][sel["control"]][0] for r in rows.values()]
pair=read(D/"test-results.json")["paired"][sel["control"]]["FS2048"]
assert len(rows)==2000 and len({v["t"] for v in rows.values()})==1207
assert (sum(v>0 for v in vals),sum(v<0 for v in vals))==(pair["wins"],pair["losses"])==(21,32)
print(f"Verified {len(manifest)} files and all 2,000 outcomes of the preselected contrast.")
import hashlib,json,re
from pathlib import Path
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_bytes())
files=load(D/"manifest.json")
for f,h in files.items():assert sha(D/f)==h,f
browser=load(D/"browser-receipt.json");source=load(D/"source.json");ref=load(D/"verification.json")
assert sha(D/"index.html")==source["output"]==browser["html"]
assert sha(D/"ui-oracle.json")==ref["oracle"]==browser["oracle"]
assert sha(D/"source.json")==ref["source"]
assert all(sha(D/"qa"/k)==v for k,v in browser["screenshots"].items())
assert browser["oracle_states"]==ref["oracle_states"]==320 and ref["candidates"]==1826
for f in ("index.html","REPORT_RU.md"):
 text=(D/f).read_text(encoding="utf8")
 links=re.findall(r'href="([^"#]+)"' if f.endswith(".html") else r'\]\(([^\s)]+)\)',text)
 for link in links:
  if not link.startswith(("http:","https:")):assert (D/link).is_file(),link
print(f"Verified {len(files)} files, all local document links and 320 browser states.")
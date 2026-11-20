"""Post-hoc packet concentration, using only returned headers, not target labels."""
import collections
import gzip
import json
import re
import statistics
from pathlib import Path
D=Path(__file__).resolve().parent
HEADER=re.compile(r"(?m)^(\S+\.py)  L(\d+)-(\d+)  ([\w.]+)$")
tasks=[]
for f in sorted((D/"predictions").glob("*.json.gz")):
    q=json.loads(gzip.decompress(f.read_bytes()));row={"task":q["id"],"project":q["id"].split("-")[0],"arms":{}}
    for arm,p in q["arms"].items():
        hs=HEADER.findall(p["packet"]);assert [[a,int(b),int(c)] for a,b,c,d in hs]==p["kept"]
        owners=collections.Counter((a,d) for a,b,c,d in hs)
        row["arms"][arm]={"windows":len(hs),"distinct_owners":len(owners),"largest_owner_window_share":max(owners.values())/len(hs) if hs else 0}
    tasks.append(row)
out={}
for proj in sorted({r["project"] for r in tasks}):
    selected=[r for r in tasks if r["project"]==proj]
    out[proj]={a:{m:statistics.mean(r["arms"][a][m] for r in selected) for m in ["windows","distinct_owners","largest_owner_window_share"]} for a in ["bm25","doclink","shuffled","r6_flat"]}
(D/"diagnostic_concentration.json").write_text(json.dumps({"aggregate":out,"rows":tasks},indent=2),"utf8")
print(json.dumps(out))

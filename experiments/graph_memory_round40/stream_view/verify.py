"""Verify all stored stream endpoints against the independent signed R39 reference."""
import gzip
import json
from pathlib import Path
import sqlite3
from hashlib import sha256

D=Path(__file__).resolve().parent
src=D.parents[1]/"graph_memory_round39/provenance_packet_demo"
read=lambda f:json.loads(gzip.decompress(f.read_bytes()) if f.suffix==".gz" else f.read_bytes())
res=read(D/"results.json")
pack=read(D/"packets.json.gz")
logs=read(D/"outcomes.json.gz")
assert sha256((D/"packets.json.gz").read_bytes()).hexdigest()==res["packets"]
assert sha256((D/"outcomes.json.gz").read_bytes()).hexdigest()==res["outcomes"]
db=sqlite3.connect((src/"reader.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
reference=read(src/"reference.json")
assert set(reference)==set(pack)==set(logs)
for key in ("chronological","shuffle"):
    g=res["groups"][key]
    total=changed=0
    for q,entry in pack.items():
        cast=[r[0] for r in db.execute("select id from node where q=? order by rank",(q,))]
        steps=entry[key]
        assert all(x==sorted(set(x)) for x in steps)
        assert [cast[i] for i in steps[-1]]==reference[q]["ids"]
        assert len(steps)==logs[q][key]["steps"]
        total+=len(steps)
        changed+=int(bool(steps[0]))+sum(a!=b for a,b in zip(steps,steps[1:]))
    assert (total,changed)==(g["steps"],g["changed"])
print("Verified",len(reference),"endpoint rankings and both complete stream logs")


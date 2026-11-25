"""Secondary descriptive audit of invalidations produced by the consumer itself."""
import hashlib
import json
import random
from pathlib import Path
from store import connect,DATA

db=connect()
rows=db.execute("""
SELECT r.t,r.a,r.b,r.step,r.value_id,r.other
FROM reason r WHERE r.cause='ambiguous'
ORDER BY r.t,r.a,r.b,r.step,r.value_id
""").fetchall()
terminal={(t,a,b,step) for t,a,b,step in db.execute("""
SELECT t,a,b,hi FROM witness AS w WHERE hi IS NOT NULL AND NOT EXISTS
(SELECT 1 FROM witness AS next WHERE next.t=w.t AND next.a=w.a AND next.b=w.b AND next.lo=w.hi)
""")}
hist={t:[0,0,0,0] for (t,) in db.execute("SELECT t FROM trace ORDER BY t")}
events={}
for t,a,b,step,v,other in rows:
    hist[t][0]+=1;hist[t][1]+=int(other==b)
    if (t,a,b,step) in terminal:
        observed=events.setdefault((t,a,b,step),other)
        assert observed==other
assert set(events)==terminal
for (t,a,b,step),producer in events.items():
    hist[t][2]+=1;hist[t][3]+=int(producer==b)
assert sum(v[0] for v in hist.values())==553 and sum(v[2] for v in hist.values())==477
rng=random.Random(2112);intervals={}
for idx,label in ((0,"witness"),(2,"edge")):
    values=list(hist.values());ratios=[]
    for _ in range(10000):
        trial=rng.choices(values,k=len(values))
        den=sum(r[idx] for r in trial)
        if den:ratios.append(sum(r[idx+1] for r in trial)/den)
    ratios.sort()
    intervals[label]=[ratios[int(p*(len(ratios)-1))] for p in (.025,.975)]
result={"trajectories":hist,"ci95_trajectory_bootstrap":intervals,
        "counts_witness_total_echo_edge_total_echo":[sum(v[i] for v in hist.values()) for i in range(4)],
        "source_sha256":hashlib.sha256(DATA.read_bytes()).hexdigest(),"status":"post_hoc"}
DATA.with_name("echo-audit.json").write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8")
print(result["counts_witness_total_echo_edge_total_echo"],intervals)

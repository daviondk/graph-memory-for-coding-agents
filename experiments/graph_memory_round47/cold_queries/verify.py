"""Check the primary contrast and cumulative horizons using only the Python standard library."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import gzip,json,math
D=Path(__file__).resolve().parent
raw=json.loads(gzip.decompress((D/"timings.json.gz").read_bytes()))
results=json.loads((D/"results.json").read_bytes())
run=json.loads((D/"run.json").read_bytes())
assert sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest()==run["protocol"]
assert len(raw)==5120 and len({(q,p,r) for q,p,r,*rest in raw})==5120
assert len({q for q,*_ in raw})==40 and len({p for _,p,*_ in raw})==1280
assert run["equalities"]==102400
for h in (1,2,4,8,16):
    diffs=defaultdict(int);total_a=total_b=0
    for q,p,rep,build,mem,native in raw:
        assert len(mem)==len(native)==16 and min(build,*mem,*native)>0
        a=build+sum(mem[:h]);b=sum(native[:h]);total_a+=a;total_b+=b;diffs[p]+=b-a
    entry=results[str(h)]
    assert math.isclose(total_b/total_a,entry["speedup"])
    assert entry["pairs_faster"]==sum(x>0 for x in diffs.values())
print("Verified four repetitions, 1,280 pairs, five horizons and paired latency results.")

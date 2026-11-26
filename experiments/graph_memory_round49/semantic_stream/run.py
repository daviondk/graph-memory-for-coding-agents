"""Time semantic-head maintenance and freeze predictions before scoring any annotated spans."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import random
import sys

D = Path(__file__).resolve().parent
S = D.parent/"stream_packet"
sys.path.insert(0,str(S))
import bench
from fixture import load, save, digest
bench.D = D

def exhaustive(data,step,cap):
    live=[r for r in data.items if r[0]<=step]
    scores=dict(pair for g in data.events[:step] for pair in g)
    head=[]
    used=0
    for r in sorted(live,key=lambda r:r[1]):
        if used+r[2]>data.T:
            break
        head.append(r[1])
        used+=r[2]
    rows=[r for r in live if r[1] not in head]
    optimum = (0,0)
    for mask in range(1<<len(rows)):
        bag=[r for j,r in enumerate(rows) if mask>>j&1]
        if sum(r[2] for r in bag)+used<=data.B:
            val=sum(r[3]+sum(min(cap,scores.get(a,0))<<28 for a in r[4]) for r in bag)
            optimum=max(optimum,(val,-mask))
    return head+[r[1] for j,r in reversed(list(enumerate(rows))) if (-optimum[1])>>j&1]

def main():
    assert digest((D/"PROTOCOL_RU.md").read_bytes())=="a85d3aa86f90544d8ea58fb5d2fb2290bdb1c679f16f21b80c541a6c2b23683d"
    assert digest((S/"input.json.gz").read_bytes())==load(S/"input-seal.json")["file"]
    native=bench.library()
    bench.brute=exhaustive
    tested=bench.small(native)
    inputs=load(S/"input.json.gz")
    streams={q:bench.Input(rows,ev) for q,(_,rows,ev) in inputs.items()}
    plans=[(m,c) for m in (0,-1,16) for c in (0,4)]
    rng=random.Random(49170)
    hashes={}
    forecasts=defaultdict(dict)
    times=[]
    for rep in range(6):
        order=list(streams)
        rng.shuffle(order)
        for q in order:
            s=streams[q]
            plan=plans.copy()
            rng.shuffle(plan)
            for mode,cap in plan:
                elapsed,stats,flat,ends=s.trial(native,mode,1,cap)
                h=sha256(flat+ends).hexdigest()
                assert hashes.setdefault((q,cap),h)==h,(q,cap,mode)
                if not rep and mode==0:
                    packets=s.packs(flat,ends)
                    forecasts[q][str(cap)]={str(i):packets[i-1] for i in (8,s.st) if i<=s.st}
                if rep:
                    times.append([q,rep,mode,cap,elapsed,*stats])
        print("complete repetition",rep,flush=True)
    save(D/"packets.json.gz",forecasts)
    save(D/"timing.json.gz",times)
    save(D/"forecast-seal.json",dict(protocol=digest((D/"PROTOCOL_RU.md").read_bytes()),
        inputs=digest((S/"input.json.gz").read_bytes()),source=digest((D/"stream.cpp").read_bytes()),
        small=tested,packets=digest((D/"packets.json.gz").read_bytes()),times=digest((D/"timing.json.gz").read_bytes()),
        order=digest("".join(hashes[k] for k in sorted(hashes)).encode()),boundaries=sum(s.st for s in streams.values())))
if __name__=="__main__":
    main()

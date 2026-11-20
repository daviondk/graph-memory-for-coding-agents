"""Compare repeated observations without treating clock readings as scientific disagreements."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import random
D=Path(__file__).resolve().parent
def load(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())
def keyed(rs):
    return {(r["task"],r["direction"],r["node"]):r for r in rs}
def hashpath(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def interval(group,arm,ref):
    parts={}
    for r in group:
        v=parts.setdefault(r["task"],[0,0])
        v[0]+=r["selected"][arm]-r["selected"][ref];v[1]+=1
    values=list(parts.values())
    rng=random.Random(92103);dist=[]
    for _ in range(10000):
        a,b=map(sum,zip(*rng.choices(values,k=len(values))));dist.append(100*a/b)
    dist.sort()
    return {"pp":100*sum(v[0] for v in values)/sum(v[1] for v in values),"ci":[dist[249],dist[9749]]}
def main():
    old=D/'initial_attempt'
    roster=load(D/'roster.json')
    for f,h in load(old/'receipts.json').items():assert hashpath(old/f)==h
    assert load(D/'runtime-before.json')==load(D/'runtime-after.json')
    a,b=keyed(load(old/'outcomes.json')),keyed(load(D/'outcomes.json'))
    fields=['prior','actual','selected','old_affected','dynamic_symbols','common_symbols','changed_symbols']
    c={k:sum(a[i][k]!=b[i][k] for i in a.keys()&b.keys()) for k in fields}
    contents={f:hashpath(old/f)==hashpath(D/f) for f in ["forecasts.json.gz","graphs.json.gz","storage.json"]}
    build=lambda rr:{(r["task"],r["direction"]):r["edges"] for r in rr}
    og=build(load(old/"graphs.json.gz"));ng=build(load(D/"graphs.json.gz"))
    gd=Counter()
    for i,a0 in og.items():
        b0=ng[i]
        for context in set(a0)|set(b0):
            if set(a0.get(context,[]))!=set(b0.get(context,[])):
                gd["shared" if context=="shared" else "test"]+=1
    groups={s:[r for r in b.values() if r["direction"]==s] for s in ("fix","revert")}
    by_direction={s:{f"{arm} minus {ref}":interval(gr,arm,ref) for arm,ref in [
                ("lines","testmon"),("shared2048","symbol"),("shared2048","bloom2048"),("symbol","testmon")]} for s,gr in groups.items()}
    issues={i:{s:dict(n=sum(r["task"]==i for r in gr),flips=sum(r["task"]==i and r["changed"] for r in gr))
                for s,gr in groups.items()} for i in roster["ids"]}
    out=dict(initial_eligible=len(a),final_eligible=len(b),only_initial=len(a.keys()-b.keys()),
             only_final=len(b.keys()-a.keys()),logical_differences=c,byte_identity=contents,changed_graph_contexts=dict(gd),
             issue=issues,additional_intervals=by_direction)
    (D/"comparison.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf8")
    print("eligible",len(a),len(b),"logical differences",c,"byte identity",contents)
if __name__=="__main__":main()

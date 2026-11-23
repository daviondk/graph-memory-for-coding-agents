"""Offline independent coverage, density, active token counts and Full Support for every write/read."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean
D=Path(__file__).resolve().parent
def get(name):
    f=D/name;b=f.read_bytes();return json.loads(gzip.decompress(b) if f.suffix==".gz" else b)
def digest(f):
    with f.open("rb") as src:return hashlib.file_digest(src,"sha256").hexdigest()
def union(spans):
    parts=defaultdict(list)
    for e,p,a,b in spans:parts[e,p].append((a,b))
    out={}
    for k,vals in parts.items():
        acc=[]
        for a,b in sorted(vals):
            if acc and a<=acc[-1][1]:acc[-1]=(acc[-1][0],max(b,acc[-1][1]))
            else:acc.append((a,b))
        out[k]=acc
    return out
def measure(need,items):
    available=union(items)
    gp=sum(b-a for value in need.values() for a,b in value)
    spanlen=sum(b-a for e,p,a,b in items)
    match=sum(max(0,min(b,y)-max(a,x)) for k,g in need.items() for a,b in g for x,y in available.get(k,[]))
    return [int(match==gp),match/gp,match/spanlen if spanlen else 0]
def main():
    for f,h in get("MANIFEST_SHA256.json").items():assert digest(D/f)==h
    receipt=get("forecast-lock.json");assert receipt["projections"]==digest(D/"projection-lock.json")
    cohort={s["q"]:s for s in get("cohort.json")};truth={q:union([(s["event_id"],s["json_pointer"],s["char_start"],s["char_end"]) for s in spans]) for q,spans in get("gold-spans.json.gz").items()}
    rows={r["q"]:r for r in get("outcomes.json.gz")};assert set(rows)==set(cohort)==set(truth) and len(rows)==580
    storage=get("storage.json.gz");seen=set();n=0
    for fname,h in receipt["forecasts"].items():
        assert digest(D/fname)==h
        with gzip.open(D/fname,"rb") as f:
            for line in f:
                row=json.loads(line);t=row["t"];assert t not in seen;seen.add(t)
                blocks=row["blocks"];intervals=[(*row["addresses"][e],a,b) for e,a,b,c,d in blocks]
                for arm,(keep,reads) in row["arms"].items():
                    if keep is None:keep=list(range(len(blocks)))
                    ks=set(keep);assert len(keep)==len(ks)
                    stats=storage[t][arm]
                    assert sum(blocks[i][3] for i in keep)==stats["write_tokens"] and (arm=="all" or stats["write_tokens"]<=8192)
                    assert sum(blocks[i][4] for i in keep)==stats["bytes"]
                    persisted=[intervals[i] for i in keep]
                    for q,sel in reads.items():
                        assert cohort[q]["t"]==t and len(set(sel))==len(sel) and set(sel)<=ks
                        rt=sum(blocks[i][3] for i in sel);assert rt<=2048
                        metrics=measure(truth[q],persisted)+measure(truth[q],[intervals[i] for i in sel])+[rt]
                        assert all(abs(a-b)<1e-12 for a,b in zip(rows[q]["a"][arm],metrics,strict=True))
                        n+=1
    assert len(seen)==352 and n==580*8
    result=get("results.json")
    for part,rs in (("all580",list(rows.values())),("profile500",[row for q,row in rows.items() if cohort[q]["publication_dev500"]]),("other80",[row for q,row in rows.items() if not cohort[q]["publication_dev500"]])):
        r=result[part];assert len(rs)==r["n"]
        for arm,ms in r["metrics"].items():
            assert ms["write_full_count"]==sum(a["a"][arm][0] for a in rs) and ms["read_full_count"]==sum(a["a"][arm][3] for a in rs)
    print("verified",n,"query-policies,",n*2,"write/read evidence scores, 352 disjoint development trajectories")
if __name__=="__main__":main()

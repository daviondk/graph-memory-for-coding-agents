"""Independent sweep by stored start/end events; terminal/source confidence and observed-view counts."""
from pathlib import Path
import gzip,json,hashlib,collections,math,statistics
D=Path(__file__).resolve().parent;V=D.parent/"code_visibility";S=D.parent/"code_store"
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    s=get(D/"demand-seal.json");b=get(D/"boundary-seal.json");f=get(D/"physical-plan.json");ts=get(D/"physical-seal.json")
    assert b["data"]==sha(D/"native_boundaries.json.gz")
    assert b["code"]==sha(D/"native.py") and s["program"]==sha(D/"count.py") and f["program"]==sha(D/"physical.py")
    assert f["sqlite"]==sha(S/"storage.py") and b["previous_visibility"]==sha(V/"manifest.json")
    assert s["future"]==sha(D/"followup.json.gz") and s["prefixes"]==sha(D/"prefixes.json.gz") and ts["measurements"]==sha(D/"physical.json.gz")
    source=get(V/"events.json.gz");bound=get(D/"native_boundaries.json.gz");future=get(D/"followup.json.gz");byq={r["q"]:r for r in future}
    old={q["q"] for q in get(V/"predictions.json.gz")};assert old=={r["old"] for r in future if r["old"]}
    native=get(D/"prefixes.json.gz");count=collections.Counter()
    for r in future:
        v=source[r["rid"]]["events"];n=bound[r["rid"]];p=native[r["q"]]["path"]
        assert any(e[0]==r["edit"] and e[1:3]==["edit",p] and e[3]["matched"] for e in v)
        assert any(e[0]==r["prev"] and e[1:3]==["read",p] and e[3] for e in v)
        for mode in ("strict","ignore_opaque"):
            x=r[mode];start=r["edit"];end=x["end"];include_end=x["stop"].startswith("trace_end")
            ev=[e for e in v if start<e[0] and (e[0]<end or include_end and e[0]==end)]
            views=[e for e in ev if e[1:3]==["read",p]]
            assert x["reads"]==sum(bool(z[3]) for z in views) and x["any_view"]==len(views)
            assert x["numbered_view"]==sum(z[4]>0 for z in views)
            if mode=="strict":assert not any(e[1]=="barrier" for e in ev)
            if x["stop"]=="mutation":
                assert any(end==b and ph==hashlib.sha256(p.encode()).hexdigest() for a,b,cmd,ph in n["successful_writes"])
            elif x["stop"]=="finished":assert end==n["finished"] and n["run_error"] is False
            elif x["stop"]=="opaque":assert any(e[:2]==[end,"barrier"] for e in v)
        if r["cohort"]=="main" and r["prefix"]=="clean":
            x=r["strict"];count["n"]+=1
            count["verified_zero"]+=x["reads"]==0 and x["stop"] in ("mutation","finished")
            count["positive"]+=x["reads"]>0
    assert (count["n"],count["verified_zero"],count["positive"])==(676,108,102)
    pool=sorted((r["q"] for r in future if r["prefix"]=="clean" and r["strict"]["stop"] in ("mutation","finished")),key=lambda q:hashlib.sha256(("R37-natural-demand|"+q).encode()).digest())
    assert len(pool)==f["eligible"] and f["panel"]==pool[:128]
    tm=get(D/"physical.json.gz");result=get(D/"results.json")
    for mode,rows in tm.items():
        for m in "AML":
            means=[]
            for q,v in rows.items():
                n=byq[q]["strict"]["reads"] if mode=="observed" else 1
                assert len(v)==6 and all(rep[m][7]==n for rep in v)
                if n==0:assert all(rep[m][1]==rep[m][3]==rep[m][6]==0 for rep in v)
                means.append(statistics.mean(rep[m][0]+rep[m][1] for rep in v))
            assert math.isclose(statistics.mean(means),result["physical"][mode]["all"]["wall_ns"]["means"][m])
    print("Verified",len(future),"windows, 2 censoring definitions, 1282 prior matches and six paired repeats on 128 episodes.")
if __name__=="__main__":run()

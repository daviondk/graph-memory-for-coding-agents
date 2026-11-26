"""Measured SQLite workload with observed counts; storage operators never receive the schedule."""
from native import D,V,S,sha,get,save,h
from pathlib import Path
from time import perf_counter_ns
from itertools import permutations
from tempfile import TemporaryDirectory
import sys,sqlite3
sys.path.insert(0,str(S))
from benchmark import cycles
from storage import initialize,transition,lookup,rows
METHODS="AML"
def reference(item):
    out=dict(item["receipt"])
    if item["start"] is None:return sorted(out.items())
    candidates={}
    for n,s in item["base"]:
        if item["start"]<=n<=item["end"]:continue
        dst=n if n<item["start"] else n+item["delta"]
        if dst not in out:candidates[dst]=s
    for n in sorted(candidates,key=lambda n:h("R37-128|"+item["path"]+"|"+str(n)))[:128-len(out)]:out[n]=candidates[n]
    return sorted(out.items())
def prepare():
    allf=get(D/"followup.json.gz")
    eligible=[r for r in allf if r["prefix"]=="clean" and r["strict"]["stop"] in ("mutation","finished")]
    panel=sorted((r["q"] for r in eligible),key=lambda q:h("R37-natural-demand|"+q))[:128]
    return save(D/"physical-plan.json",dict(panel=panel,eligible=len(eligible),program=sha(Path(__file__)),previous=sha(S/"manifest.json"),sqlite=sha(S/"storage.py"),
               schedule=sha(D/"followup.json.gz"),input=sha(D/"prefixes.json.gz"),protocol=sha(D/"PROTOCOL_RU.md"),addendum=sha(D/"TIMING_ADDENDUM_RU.md")))
def bench():
    r=get(D/"physical-plan.json");panel=r["panel"];prefix=get(D/"prefixes.json.gz");outcomes={v["q"]:v for v in get(D/"followup.json.gz")};orig=get(S/"reference.json.gz")
    items={};expected={}
    for i,q in enumerate(panel):
        item=prefix[q];items[i]={**item,"base":rows(item["base"]),"receipt":dict(rows(item["receipt"]))}
        expected[i]=reference(items[i]);old=outcomes[q]["old"]
        if old:assert expected[i]==rows(orig[old])
    vals={mode:{q:[] for q in panel} for mode in ("observed","uniform")}
    orders=list(permutations(METHODS))
    with TemporaryDirectory(dir=D,prefix="sqlite_") as td:
        for rep in range(-1,6):
            modes=("observed","uniform") if rep%2==0 else ("uniform","observed")
            for mode in modes:
                db={k:initialize(Path(td)/(k+mode+str(rep)+".db"),k,items) for k in METHODS}
                for i,q in enumerate(panel):
                    trial={};order=orders[(int(h("natural-order|"+q)[:16],16)+max(rep,0))%6]
                    for k in order:
                        c=db[k];item=items[i]
                        w=perf_counter_ns();cc=cycles()
                        writes,pre_rows,_=transition(c,k,i,item)
                        cw=cycles()-cc;ww=perf_counter_ns()-w
                        nr=outcomes[q]["strict"]["reads"] if mode=="observed" else 1
                        if nr:
                            w=perf_counter_ns();cc=cycles()
                            answers=[lookup(c,k,i,item) for _ in range(nr)]
                            cr=cycles()-cc;wr=perf_counter_ns()-w
                            assert all(out==expected[i] for out,_ in answers)
                            rd=sum(n for _,n in answers)
                        else:wr=cr=rd=0
                        trial[k]=[ww,wr,cw,cr,writes,pre_rows,rd,nr]
                    if rep>=0:vals[mode][q].append(trial)
                if rep==-1:
                    for k,c in db.items():
                        for i,q in enumerate(panel):assert lookup(c,k,i,items[i])[0]==expected[i]
                for con in db.values():con.close()
    f=save(D/"physical.json.gz",vals);save(D/"physical-seal.json",dict(plan=sha(D/"physical-plan.json"),measurements=f,sqlite=sqlite3.sqlite_version))
    print("panel",len(panel),"observed reads",sum(outcomes[q]["strict"]["reads"] for q in panel),"zero",sum(outcomes[q]["strict"]["reads"]==0 for q in panel))
if __name__=="__main__":prepare();bench()

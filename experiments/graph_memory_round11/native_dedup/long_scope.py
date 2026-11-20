"""Secondary matched whole-session context comparison with the frozen R11 encoders."""
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import sys
from exercise import ROOT,READ,load,put,raw,sha,REF
from audit import packet,ci
sys.path.insert(0,str(READ))
from replay import session

def run(args):
    task,record,tr=args;views=record["views"];hist={};metrics=Counter()
    for v,r in zip(views,tr):
        body=raw(v);text=r["compression"]["out"];ref=REF.fullmatch(text)
        seen=hist.setdefault(v["path"],{})
        if ref:
            assert r["expansion"]["out"]==body
            matched=any(digest.startswith(ref[1]) for digest in seen)
            metrics["requires_external_db"]+=not matched
            if not matched:text=body
        assert ref or text==body
        if text==body:seen[sha(body.encode())]=True
        metrics["strict"]+=packet(v["turn"],text)
    for mode in ["visible","runtime"]:
        for method in ["raw","single","union","whole"]:
            rows=session(views,record["events"]+1,mode,method)
            metrics[(method if mode=="visible" else "runtime_"+method)]=sum(r["tokens"] for r in rows)
    return dict(task=task,panel=record["panel"],strict=metrics["strict"],**{k:v for k,v in metrics.items() if k!="strict"})

def main():
    data=load(READ/"views.gz");receipt=load(ROOT/"native-receipts.gz")
    with ThreadPoolExecutor(4) as ex:rows=list(ex.map(run,[(k,data[k],receipt[k]["records"]) for k in sorted(data)]))
    stat={}
    for panel in ["all",*sorted(set(r["panel"] for r in rows))]:
        subs=[r for r in rows if panel=="all" or panel==r["panel"]]
        s=Counter()
        for r in subs:s.update({k:v for k,v in r.items() if type(v)==int})
        stat[panel]=dict(totals=s,points=100*(s["strict"]-s["union"])/s["raw"],ci95=ci(subs))
    put(ROOT/"long-tasks.gz",rows);put(ROOT/"long-results.json",stat)
    print(stat)
if __name__=="__main__":main()

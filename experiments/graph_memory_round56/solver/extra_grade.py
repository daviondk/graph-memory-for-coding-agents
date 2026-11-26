"""Evaluate the matched opportunity controls; reuse a result only for identical input and answer."""
from collections import Counter
import statistics
from study import *
from grade import parse_answer,signflip
from isolation import execute
from extension import MODELS

def main():
    refs=read("extra-assignments.json.gz");sel=read("selections.json.gz");primary=read("execution.json.gz")
    ans=read("extra-answers.json.gz");oldans=read("answers.json.gz");cal=read("calibration.json.gz")
    prior_inputs=read("assignments.json.gz")
    seal=read("extra-answer-seal.json");assert digest((HERE/"extra-answers.json.gz").read_bytes())==seal["answers"]
    marks={};measured={};jobs={}
    for q,arms in refs.items():
        t=sel[q]["task"]
        for a,v in arms.items():
            h=v["hash"];k=q+"|"+h
            if k in marks:continue
            if k in primary["parse_status"]:
                assert oldans[h]==ans[h]
                marks[k]=primary["parse_status"][k]
                if k in primary["measured"]:measured[k]=primary["measured"][k]
            else:
                src,marks[k]=parse_answer(ans[h]["text"],t["name"])
                if src:jobs[k]=dict(id=k,repo=t["repo"],path=t["path"],name=t["name"],kind="model",answer=src)
    measured.update(execute(list(jobs.values())))
    records={}
    for q,arms in refs.items():
        n=cal[q+"|reference"]["run"];r={}
        for a,v in arms.items():
            h=v["hash"];k=q+"|"+h
            e=measured.get(k,{})
            good=n-e["failed"] if e.get("run")==n else 0
            r[a]=dict(ok=good==n,good=good,total=n,hash=h)
        records[q]=r
    stats={}
    for a in MODELS:
        ds=[r[a] for q,r in records.items()]
        stats[a]=dict(n=len(ds),pass1=sum(d["ok"] for d in ds),passed_examples=sum(d["good"] for d in ds),examples=sum(d["total"] for d in ds))
    contrasts={}
    for aa,bb in [("file8","hash8"),("call_cascade","full_bm25"),("call_cascade","call_full"),("call_cascade","file8")]:
        d={q:int(r[aa]["ok"])-int(r[bb]["ok"]) for q,r in records.items()}
        b=[sum(x for q,x in d.items() if q.startswith(repo+"|")) for repo in SPECS]
        contrasts[aa+" vs "+bb]=dict(wins=sum(x>0 for x in d.values()),losses=sum(x<0 for x in d.values()),ties=sum(x==0 for x in d.values()),
                                delta_pp=100*sum(d.values())/len(d),repo_signflip_p=signflip(b),
                                different=sum(r[aa]["hash"]!=r[bb]["hash"] for r in refs.values()),by_repo=b)
    write("extra-execution.json.gz",dict(measured=measured,status=marks,new_jobs=len(jobs)))
    write("extra-records.json.gz",records)
    write("extra-results.json",dict(summaries=stats,contrasts=contrasts,
             shorter_than_original=sum(x["file8"]["evidence"]<prior_inputs[q]["file8"]["evidence"] for q,x in refs.items()),
             stage=dict(Counter(r["stage"] for r in read("extra-selections.json.gz").values()))))
    print(stats,contrasts)
if __name__=="__main__":
    main()

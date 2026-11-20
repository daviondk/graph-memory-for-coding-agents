"""Matched capacity and uniform anchor ablations; registered after primary analysis."""
from collections import defaultdict
import gzip
import json
from replay import Memory
from extract import ROOT, digest, pack, rows, write_json


def main():
    seal=json.loads((ROOT/"results_lock.json").read_bytes())
    assert all(digest(ROOT/s)==v for s,v in seal["files"].items())
    summary = defaultdict(lambda: defaultdict(float))
    with gzip.GzipFile(str(ROOT/"ablation_rows.gz"),"wb",mtime=0) as out:
        for q in rows(ROOT/"observations.gz"):
            for cap in (128,512):
                for k in (1,4):
                    s=summary[f"{q['panel']}/{cap}/{k}"]
                    m=Memory(cap)
                    for t,(req,ev) in enumerate(zip(q["requests"],q["events"],strict=True)):
                        if req:
                            path,limits=req
                            p,anc,_=m.forecast(path,q["id"],t)
                            # The fractional control integrates over every candidate with its true probability.
                            shown=set(ev[2])
                            exp=sum(a in shown for a in anc)/len(anc) if anc else int(p[2] in shown)
                            useful=int(p[2] in shown)
                            best=m.codec(path,limits)[0][-1] if limits else 0
                            rec=dict(id=q["id"], panel=q["panel"],cap=cap,k=k,t=t,uniform=exp,first=useful,
                                     size=len(m.serial()),transport=best,range=bool(limits))
                            out.write(pack(rec)+b"\n")
                            s["n"]+=1
                            s["hit_first"]+=useful
                            s["uniform_expected_hits"]+=exp
                            s["state_bytes_total"]+=rec["size"]
                            s["codec_bytes"]+=best
                            s["n_range"]+=bool(limits)
                        previous=m.inventory()
                        if ev and ev[0]=="search":
                            # K anchors are retained *before* the memory manager enforces its byte cap.
                            m.advance([ev[0],ev[1],ev[2][:k]])
                        else:
                            m.advance(ev)
                        now=m.inventory()
                        if now!=previous:
                            s["display_bytes"]+=len(pack(now))
                    s["peak"]=max(s["peak"],m.peak)
    for s in summary.values():
        s["mean_state_bytes"]=s["state_bytes_total"]/s["n"]
    write_json("ablation_results.json",summary)
    write_json("ablation_lock.json",{s:digest(ROOT/s) for s in ["ablation.py","ABLATION_PROTOCOL_RU.md",
               "results_lock.json","ablation_results.json","ablation_rows.gz"]})


if __name__=="__main__":
    main()

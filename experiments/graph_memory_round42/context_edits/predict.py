"""Seal the two operational ranks before loading post-edit content for validation."""
import time
from collections import Counter
from local import *
from mechanism import match,project


def main():
    actions=read(D/"action-lines.json.gz");seal=read(D/"action-seal.json")
    assert seal["actions"]==sha(D/"action-lines.json.gz") and seal["tokenization"]==sha(D/"mechanism.py")
    events=signed(G,"selections.json.gz");plans=signed(G,"guarded-plans.json.gz")
    structural=signed(S,"predictions.json.gz");schedule=signed(V,"schedule.json.gz");out={}
    start_time=time.perf_counter()
    for row in events:
        key=case_id(row);a=actions[key];st=structural[key];at=row["at"];rid=row["run"]
        ready,_=plans[rid][str(at)];path=row["path"]
        candidates=[(i,p,c,u) for i,p,l,h_,c,u,_ in ready]
        local=[(i,l,v) for i,p,l,v,*_ in ready if p==path]
        assert list(select(candidates)[0])==row["old"]==st["old"]
        clock=time.perf_counter();edge,inner,stats=match(a["old"],a["new"]);align=time.perf_counter()-clock
        def mappings(e):
            mm={}
            for i,lo,hi in local:
                dest=project(lo,hi,row["start"],row["end"],row["delta"],e)
                if dest is not None:mm[str(i)]=dest
            return mm
        unchanged=mappings({});assert unchanged==st["maps"]["range"]
        maps={};choices={};times={};dp={}
        for method,lookup in (("edges",edge),("local",inner)):
            ts=time.perf_counter();res=mappings(lookup);times[method]=time.perf_counter()-ts
            maps[method]=res
            ts=time.perf_counter()
            sol,_,_=select([r for r in candidates if r[1]!=path or str(r[0]) in res])
            dp[method]=time.perf_counter()-ts;choices[method]=list(sol)
        assert unchanged.items()<=maps["edges"].items()<=maps["local"].items()
        out[key]=dict(old=row["old"],held=row["held"],issue=row["issue"],repo=h(schedule[rid]["repo"]),group=row["group"],
                positions=maps,choices=choices,stats=stats,resource=dict(align_s=align,map_s=times,dp_s=dp,bytes=a["bytes"],
                full_source_bytes=st["cost"]["bytes"],old_lines=len(a["old"]),new_lines=len(a["new"])),
                target_selected=bool(row["cost"]["old_selected_affected"]))
    assert len(out)==2696 and sum(v["held"] for v in out.values())==1071
    save("predictions.json.gz",out)
    save("forecast-seal.json",dict(predictions=sha(D/"predictions.json.gz"),actions=sha(D/"action-seal.json"),
          controls=sha(S/"predictions.json.gz"),plans=sha(G/"guarded-plans.json.gz"),scope=sha(V/"schedule.json.gz"),
          code={f:sha(D/f) for f in ("PROTOCOL_RU.md","predict.py","mechanism.py","local.py")},
          seconds=time.perf_counter()-start_time))
    print("Frozen",len(out),"local-context and ablation forecasts.")


if __name__=="__main__":main()


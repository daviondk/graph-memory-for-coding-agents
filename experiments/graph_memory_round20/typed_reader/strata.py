"""Post hoc description of the degree prior across authored modes and source-event dispersion; no retraining."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/"holdout80"))
from heldout import differences
import study as s

def main():
    official=s.read(s.OFF/"outcomes.json.gz")
    mode={r["q"]:r["memory_mode"] for r in official if r["view"]=="flat" and r["arm"]=="prefix"}
    g=s.read(s.OFF/"gold-spans.json.gz")
    cat={q:{m,"single_event" if len({z["event_id"] for z in g[q]})==1 else "multiple_events"} for q,m in mode.items()}
    standard=[r for r in s.read(HERE/"outcomes.json.gz") if r["arm"]=="dense"]
    out={}
    for stage in ("dev","train"):
        corr=[r for r in s.read(HERE/"mechanism"/("test-"+stage)/"outcomes.json.gz") if r["arm"]=="role_degrees"]
        for group in sorted(set.union(*cat.values())):
            rows=[r for r in standard+corr if r["policy"]=="prefix" and group in cat[r["q"]]]
            d=differences(rows,"role_degrees")
            out[stage+"/"+group]={"pair":d,"full":{arm:sum(r["full_support"] for r in rows if r["arm"]==arm) for arm in ("dense","role_degrees")}}
    s.put(HERE/"strata.json",out)
    print({k:(v["pair"]["full_support"]["q"],round(v["pair"]["full_support"]["delta"],3)) for k,v in out.items()},flush=True)
if __name__=="__main__":main()

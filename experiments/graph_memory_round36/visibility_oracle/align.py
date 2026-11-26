"""Audit unprojectable pairs independently of the streaming implementation."""
from pathlib import Path
import importlib.util
src=Path(__file__).with_name("study.py");spec=importlib.util.spec_from_file_location("visibility_intervals",src)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
D,l,windows,sets,pair_h=mod.D,mod.l,mod.windows,mod.sets,mod.pair_h
def main():
    ours=l.read(D/"histories.json.gz");changed={};n_hist=0
    for sh in range(8):
        units={}
        for row in l.read(l.ref.TR/f"forecasts-main-{sh}.json.gz"):
            if row["t"] not in units:
                units[row["t"]]={v["source_spans"][0]["event_id"] for v in row["rr"] if v["node_id"].startswith("output-content:")}
        for _,obj in l.env.pilot.stream(l.env.RAW/f"trajectories-{sh:05d}.jsonl"):
            t=obj["session_id"]
            if t not in units:continue
            n_hist+=1;tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1])
            empty={e.call_id for e in tr.events if e.event_type=="tool_output" and e.event_id not in units[t]}
            if not empty:continue
            life=windows(tr.events)
            for cut,j in zip(("25","50","75","100"),l.parent.cuts_for(tr.events)):
                raw=sets(life,j);valid={k:{(a,b) for a,b in v if a not in empty and b not in empty} for k,v in raw.items()}
                assert all(len(raw[k])==ours[t][cut]["call_pairs"][k] and pair_h(raw[k])==ours[t][cut]["identities"][k] for k in raw)
                if any(raw[k]!=valid[k] for k in raw):
                    changed[t+"/"+cut]={"empty_output_groups":len(empty),"projected_calls":{k:len(v) for k,v in valid.items()},
                        "projected_identities":{k:pair_h(v) for k,v in valid.items()}}
    assert n_hist==1207
    l.save(D/"call-alignment.json",{"adjustments":changed,"histories":n_hist,"input":l.sha(D/"histories.json.gz"),"code":l.sha(D/"align.py")})
    print("Call containment corrections in",len(changed),"history/cut states",flush=True)
if __name__=="__main__":main()

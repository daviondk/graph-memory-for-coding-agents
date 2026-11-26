"""Run independent finite-capacity writers on the entire visible prefix across every path."""
import time
from common import *
from source import capture
from writer import Writer
sys.path.insert(0,str(C))
from mechanism import match,project


def readback(writer,body,path,edit,receipt,action,catalog):
    start,end,delta=edit["start"],edit["end"],edit["delta"]
    maps=action;newend=end+delta;records=[]
    for (pp,old),(dg,size,first,last,freq) in writer.rows.items():
        if pp!=path:continue
        loc=project(old,old,start,end,delta,maps)
        if loc is None:continue
        new=loc[0]
        if new in receipt:continue
        records.append((old,new,dg,size,last))
    records.sort(key=lambda v:(-v[4],max(start-v[1],v[1]-newend,0),abs(v[1]-start),v[1],v[2]))
    all_ids=[];sent=[];used=0
    for old,new,dg,size,_ in records:
        tup=(old,new,dg,size)
        if tup not in catalog:catalog[tup]=len(catalog)
        idx=catalog[tup];all_ids.append(idx)
        if used+size+1<=2048:
            sent.append(idx);used+=size+1
    return {"all":all_ids,"read":sent,"wire":writer.wire(body),"emitted_bytes":used}


def main():
    assert sha(D/"PROTOCOL_RU.md")=="5a3dc2d159346e8ade61f7e22861ab2f1a348eae2d67e8582c88c095f1b7aa4c"
    cases=signed(G,"selections.json.gz");ft=signed(F,"packets.json.gz");actions=signed(C,"action-lines.json.gz")
    desired=defaultdict(dict)
    for row in cases:desired[row["run"]][row["at"]]=row
    start=time.perf_counter();events,reads,bodies=capture(cases);project_time=time.perf_counter()-start
    ts=time.perf_counter();output={};maxima=Counter();evictions=Counter();conflicts=Counter();sum_time=Counter()
    for run,frames in events.items():
        writers={label(m,cap):Writer(m,cap) for cap in CAPS for m in MODES}
        writers.update({label(m,None):Writer(m,None) for m in ("latest","lru")})
        for at,kind,path in frames:
            if kind=="read":
                values=reads[run][at]
                for name,w in writers.items():
                    t0=time.perf_counter();w.read(path,at,values);sum_time[name]+=time.perf_counter()-t0
                continue
            if kind in ("barrier","gap","finish"):
                for w in writers.values():w.clear()
                continue
            if at in desired[run]:
                row=desired[run][at]
                assert kind=="write_start" and path==row["path"]
                key=h(run+"/"+str(row["receipt"]));p=ft[key];lit=actions[key]
                _,mapping,_=match(lit["old"],lit["new"]);receipt=dict(p["receipt"]);catalog={};pred={}
                for name,w in writers.items():
                    pred[name]=readback(w,bodies,path,row,receipt,mapping,catalog)
                output[key]=dict(issue=p["issue"],repo=p["repo"],group=p["group"],held=p["held"],run=run,
                                 at=at,arms=pred,candidates=list(catalog))
            if kind in ("write_start","other","edit"):
                for w in writers.values():w.remove_path(path)
        for name,w in writers.items():
            maxima[name]=max(maxima[name],w.max_size);evictions[name]+=w.evicted;conflicts[name]+=w.conflicts
    assert len(output)==len(cases)==2696
    save("forecasts.json.gz",output);save("forecast-seal.json",dict(forecasts=sha(D/"forecasts.json.gz"),
        input=sha(D/"input-seal.json"),action_policy=sha(C/"manifest.json"),revision_cases=sha(G/"manifest.json"),
        n_cases=len(cases),runs=len(events),peak_wire=maxima,evictions=evictions,prior_conflicts=conflicts,finite_update_s=sum_time,
        project_s=project_time,simulation_s=time.perf_counter()-ts,protocol=sha(D/"PROTOCOL_RU.md"),
        code={s:sha(D/s) for s in ("writer.py","source.py","simulate.py","common.py")}))
    print("Sealed",len(output),"edit forecasts from",len(events),"strict stream prefixes and",len(writers),"writer-cap settings.")
if __name__=="__main__":main()


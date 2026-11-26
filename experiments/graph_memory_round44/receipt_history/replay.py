from rec_data import *
import time
def main():
    assert sha(HERE/"PROTOCOL_RU.md")=="54fa5101184a00a555104dd3348c5da181d99069875dde9a247d658f4c0d844f"
    started=time.perf_counter();frames,views,receipts,bodies=prepare();proj=time.perf_counter()-started;started=time.perf_counter()
    old=signed(PREV,"forecasts.json.gz");target=defaultdict(dict)
    for r in signed(G,"selections.json.gz"):target[r["run"]][r["at"]]=r
    ft=signed(F,"packets.json.gz");acts=signed(C,"action-lines.json.gz")
    saved={};peak=Counter();evicted=Counter()
    for run,events in frames.items():
        writers={(mode,cap):Writer("lru",cap) for mode in MODES_R for cap in (*CAPS,None)}
        for at,kind,path in events:
            if kind=="read":
                for (mode,_),w in writers.items():
                    if mode!="receipts":w.read(path,at,views[run][str(at)])
                continue
            if kind in ("barrier","gap","finish"):
                for w in writers.values():w.clear()
                continue
            if at in target[run]:
                row=target[run][at];k=h(run+"/"+str(row["receipt"]));p=ft[k];action=acts[k];assert kind=="write_start" and path==row["path"]
                _,mapping,_=match(action["old"],action["new"]);receipt=dict(p["receipt"]);catalog={};arm={}
                for (mode,cap),w in writers.items():
                    ar=readback(w,bodies,path,row,receipt,mapping,catalog);arm[label(mode,cap)]=ar
                    if mode=="views":
                        original=old[k]["arms"][label("lru",cap)];assert ar["wire"]==original["wire"] and ar["emitted_bytes"]==original["emitted_bytes"]
                        li=list(catalog)
                        for t in ("all","read"):assert [list(li[i]) for i in ar[t]]==[old[k]["candidates"][i] for i in original[t]]
                saved[k]=dict(issue=p["issue"],repo=p["repo"],group=p["group"],held=p["held"],run=run,
                              at=at,arms=arm,candidates=list(catalog))
            if kind in ("write_start","edit","other"):
                for w in writers.values():w.remove_path(path)
            if kind=="edit" and at in receipts.get(run,{}):
                for (mode,_),w in writers.items():
                    if mode!="views":w.read(path,at,receipts[run][at])
        for (mode,cap),w in writers.items():
            n=label(mode,cap);peak[n]=max(peak[n],w.max_size);evicted[n]+=w.evicted
    assert set(saved)==set(old) and len(saved)==2696
    store_file("forecasts.json.gz",saved);store_file("forecast-seal.json",dict(forecasts=sha(HERE/"forecasts.json.gz"),input=sha(HERE/"input-seal.json"),
        protocol=sha(HERE/"PROTOCOL_RU.md"),controls=sha(PREV/"forecasts.json.gz"),runs=len(frames),rows=len(saved),peak_wire=peak,
        evictions=evicted,build_seconds=proj,predict_seconds=time.perf_counter()-started,program=sha(HERE/"replay.py")))
    print("Sealed",len(saved),"past-receipt forecasts; all views-only arms equal R44.")
if __name__=="__main__":main()

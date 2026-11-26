"""Open future observations only after fixed packets were signed, preserving published stopping/censoring rules."""
from collections import defaultdict
import importlib.util
import sys

import pyarrow.parquet as pq
from data import *


def main():
    packets=read(D/"packets.json.gz");seal=read(D/"packet-seal.json")
    assert seal["packets"]==sha(D/"packets.json.gz")
    rows=bind(E,"followup.json.gz")
    follow={(r["rid"],r["edit"]):r for r in rows}
    corpus=bind(H,"events.json.gz")
    windows={};desired=defaultdict(dict)
    for k,p in packets.items():
        rid,ack=p["run"],p["ack"];q=follow[rid,ack];s=q["strict"];end=s["end"]
        assert q["prefix"]=="clean" and h(q["issue"])==p["issue"] and h(q["repo"])==p["repo"]
        seq=corpus[rid]["events"]
        start_event=next(e for e in seq if e[0]==ack)
        assert start_event[1]=="edit";path=start_event[2]
        selected=[]
        for e in seq:
            index=e[0]
            if not ack<index<=end or (index==end and s["stop"] not in ("trace_end_error","trace_end_unverified")):continue
            if e[1]=="read" and e[2]==path and e[3]:
                ix=int(index);selected.append(ix)
                if ix in desired[rid]:assert desired[rid][ix]==e[3]
                desired[rid][ix]=e[3]
        assert len(selected)==s["reads"] and (selected[0] if selected else None)==s["first"],(s["stop"],len(selected),s["reads"])
        windows[k]=dict(reads=selected,stop=s["stop"],closed=s["stop"] in ("mutation","finished"))
    # Reuse the precise original read-output parser for the true denominators and bytes of each returned line.
    foreign=H/"project.py";spec=importlib.util.spec_from_file_location("signed_handoff_read_projection",foreign)
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    RAW=Path("D:/CodexResearch/x20-r31-handoff");seen={};tape=defaultdict(dict)
    for shard in read(RAW/"files.json")["events"]:
        f=RAW/shard["file"];assert sha(f)==shard["sha"]
        for batch in pq.ParquetFile(f).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for j,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in seen:seen[run]=h(run)
                rid=seen[run]
                if rid not in desired or at not in desired[rid]:continue
                ob=json.loads(batch.column(2)[j].as_py())["raw"]["observation"]
                assert ob["command"]=="view" and not ob["is_error"]
                parsed=native.numbered(native.textof(ob),ob["path"],False)
                pairs=native.slots(parsed);assert pairs==desired[rid][at]
                tape[rid][str(at)]=[[n,d,len(parsed[n].encode())] for n,d in pairs]
    assert all(set(map(str,reads))==set(tape[run]) for run,reads in desired.items())
    save("requests.json.gz",dict(windows=windows,by_run=tape))
    save("request-seal.json",dict(requests=sha(D/"requests.json.gz"),packets=sha(D/"packet-seal.json"),
         labels=sha(E/"followup.json.gz"),visibility=sha(H/"events.json.gz"),parser=sha(foreign),program=sha(D/"demand.py")))
    print("Linked",len(windows),"strict windows,",sum(len(v["reads"]) for v in windows.values()),"informative view incidences.")


if __name__=="__main__":main()


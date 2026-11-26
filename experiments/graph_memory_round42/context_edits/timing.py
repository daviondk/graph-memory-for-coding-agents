"""Cost-only replay after evaluation: three timed encodings per visible action, independent edge-only control."""
import statistics
import time
from collections import defaultdict
import pyarrow.parquet as pq
from local import *
from mechanism import tokens,match

def edges_only(old,new):
    i=0;j=len(old);k=len(new)
    while i<min(j,k) and old[i]==new[i]:i+=1
    while j>i and k>i and old[j-1]==new[k-1]:j-=1;k-=1
    return {q:q for q in range(i)} | {q:q-j+k for q in range(j,len(old))}

def main():
    actions=read(D/"action-lines.json.gz")
    wanted=defaultdict(dict)
    for row in signed(G,"selections.json.gz"):wanted[row["run"]][row["at"]]=row
    history={};out={}
    for shard in read(RAW/"files.json")["events"]:
        f=RAW/shard["file"];assert sha(f)==shard["sha"]
        for batch in pq.ParquetFile(f).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for j,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in history:history[run]=h(run)
                rid=history[run]
                if rid not in wanted or at not in wanted[rid]:continue
                key=case_id(wanted[rid][at]);rec=json.loads(batch.column(2)[j].as_py())["raw"]["action"]
                inp=(rec["old_str"],rec["new_str"]);dur=defaultdict(list)
                for trial in range(3):
                    clock=time.perf_counter_ns();l,r=map(tokens,inp);dur["tokenization_ns"].append(time.perf_counter_ns()-clock)
                    assert l==actions[key]["old"] and r==actions[key]["new"]
                    sequence=("edges","bounded") if (trial+int(key[0],16))%2 else ("bounded","edges")
                    for m in sequence:
                        clock=time.perf_counter_ns()
                        if m=="edges":edges=edges_only(l,r)
                        else:e,full,_=match(l,r)
                        dur[m+"_ns"].append(time.perf_counter_ns()-clock)
                    assert edges==e and edges.items()<=full.items()
                out[key]={k:int(statistics.median(x)) for k,x in dur.items()}
    assert set(actions)==set(out)
    save("timing.json.gz",out);save("timing-seal.json",dict(rows=sha(D/"timing.json.gz"),program=sha(D/"timing.py"),
         actions=sha(D/"action-lines.json.gz"),repetitions=3,measurement="within-action median in ns; same raw visible literals"))
    print("Measured encoding, edge alignment and bounded alignment on",len(out),"actions.")
if __name__=="__main__":main()


"""Re-derive interior validation targets from public successor observations as inert data."""
from pathlib import Path
from handoff import PRIOR,D,P,sha,get,save,h
from extract import norm,extract_lines,HEADER,cohort
import json
import pyarrow.parquet as pq
def main():
    seal=get(D/"seal.json");assert sha(D/"packets.json.gz")==seal["packets"]
    runs,_=cohort();ids={rid for rid,x in runs.items() if x["handoff_view"]=="repo_only" and x["role"]=="takeover"}
    kept={};files=get(P/"files.json")["events"]
    for ref in files:
        path=P/ref["file"];assert sha(path)==ref["sha"]
        for batch in pq.ParquetFile(path).iter_batches(batch_size=96,columns=["run_id","event_index","event_type","source_json_valid","event_json"]):
            for j,(rid,idx,typ,valid) in enumerate(zip(*(batch.column(x).to_pylist() for x in ("run_id","event_index","event_type","source_json_valid")))):
                if not valid or rid not in ids or typ!="ObservationEvent" or (rid in kept and kept[rid][0]<=idx):continue
                e=json.loads(batch.column("event_json")[j].as_py()).get("raw",{}).get("observation",{})
                if e.get("kind")!="FileEditorObservation" or e.get("command")!="view" or e.get("is_error"):continue
                addr=norm(e.get("path"))
                if not addr:continue
                body="\n".join(a["text"] for a in e.get("content",[]) if isinstance(a,dict) and a.get("type")=="text" and isinstance(a.get("text"),str))
                if not any(HEADER.search(l) and norm(HEADER.search(l)[1])==addr for l in body.splitlines()):continue
                kept[rid]=(idx,addr,extract_lines(body))
    old={z["q"]:z["target"] for z in get(P/"targets.json.gz")};gold={}
    for rid in ids:
        q=h(rid);t=old[q];row=kept.get(rid)
        assert bool(row and len(row[2])>=2)==bool(t)
        if not t:continue
        _,addr,lines=row;n=len(lines)
        assert [addr,lines[0],lines[-1]]==t
        tags={"ends":[0,n-1],"inner":[(n-1)//4,(3*(n-1)+3)//4]}
        gold[q]=dict(path=addr,n=n,**{k:[[lines[j][0],h(lines[j][1])] for j in inds] for k,inds in tags.items()})
    save(D/"reference-seal.json",{"queries":len(gold),"targets":save(D/"targets.json.gz",gold),"old":sha(P/"targets.json.gz"),"code":sha(Path(__file__)),"inputs":seal["packets"]})
if __name__=="__main__":main()
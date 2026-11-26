"""Seal the sample from IDs before constructing any graphs."""
from pathlib import Path
from collections import Counter
import re,hashlib,gzip,json
D=Path(__file__).resolve().parent;W=D.parents[1];RAW=Path("D:/CodexResearch/x20-isetrace-runtime/inputs");R=W/"graph_memory_round34/live_reader";P=D.parent/"materialized_append";SW=D.parent/"streaming_witnesses"
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def key(x):return digest("isetrace-unannotated-visibility-v1/"+x)
def save(p,x):
    b=(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def main():
    reference=load(R/"plan.json")["raw"];ip=RAW/"query-authoring/isetrace-v7-raw.jsonl";mp=ip.with_suffix(".jsonl.metadata.jsonl")
    meta={};order=[];mrows=0
    for row in map(json.loads,mp.open(encoding="utf8")):
        mrows+=1;q=row["query_id"];assert q not in meta;meta[q]=row["trajectory_id"]
    for row in map(json.loads,ip.open(encoding="utf8")):order.append(row["id"])
    assert set(meta)==set(order) and len(meta)==len(order);anno=set(meta.values())
    splitpath=W/"graph_memory_round22/native_multiseed/official580/split.json.gz";spl=load(splitpath);tested=set()
    for s,rr in spl.items():
        for v in rr:assert meta[v["q"]]==v["t"];tested.add(v["t"])
    logs={};seen=0;hashes={};reg=re.compile(rb'"session_id"\s*:\s*"(traj_[^"]+)"')
    for i,p in enumerate(sorted((RAW/"trajectories").glob("*.jsonl"))):
        assert p.name==f"trajectories-{i:05d}.jsonl";state=hashlib.sha256();offset=0
        with p.open("rb") as f:
            for line in f:
                seen+=1;state.update(line);m=reg.search(line[:1600]);assert m
                sid=m.group(1).decode();assert sid not in logs;logs[sid]=[i,offset,len(line)];offset+=len(line)
        hashes[p.name]=state.hexdigest();assert hashes[p.name]==reference[p.name]
    assert set(anno)<=set(logs) and len(hashes)==8 and seen==23132
    eligible=set(logs)-anno;sample=sorted(eligible,key=key)[:512];extra=sorted(sample,key=lambda t:digest("r36-unannotated-native-outputs/v1/"+t))[:12]
    assert not set(sample)&anno and not set(sample)&tested
    plan={"protocol":sha(D/"PROTOCOL_RU.md"),"panel_code":sha(D/"panel.py"),"r36":sha(P/"manifest.json"),"streaming":sha(SW/"manifest.json"),"query":sha(ip),"metadata":sha(mp),"official_split":sha(splitpath),"raw":hashes,"metadata_rows":mrows,"question_ids":len(meta),"annotated_histories":len(anno),"raw_histories":seen,"eligible":len(eligible),"official_histories":len(tested),"panel_size":len(sample),"native_selector":"r36-unannotated-native-outputs/v1/","native":extra,"panel":{t:logs[t] for t in sample},"official_overlap":0,"metadata_overlap":0}
    if (D/"plan.json").exists():assert load(D/"plan.json")==plan
    else:save(D/"plan.json",plan)
    print(seen,len(anno),len(eligible),len(sample),len(extra),sha(D/"plan.json"),flush=True)
if __name__=="__main__":main()

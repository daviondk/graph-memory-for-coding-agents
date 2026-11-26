"""Build every snapshot from independently truncated events. Exports only numeric fixtures."""
import os
for k in ("MKL_NUM_THREADS","OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[k]="1"
from pathlib import Path
import sys,hashlib,json,gzip
from functools import lru_cache
from collections import Counter,defaultdict
D=Path(__file__).resolve().parent;W=D.parents[1]
sys.path.insert(0,str(W/"graph_memory_round22/prefix_read"))
import forecast as old
from forecast import env,ref,geometry,edges_by_name,build_provenance_graph,adapt_isetrace_record,parse_isetrace_record
def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()
def load(file):
    b=file.read_bytes();return json.loads(gzip.decompress(b) if file.suffix==".gz" else b)
def save(file,x):
    b=json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    tmp=file.with_suffix(file.suffix+".tmp");tmp.write_bytes(gzip.compress(b,compresslevel=4,mtime=0) if file.suffix==".gz" else b);tmp.replace(file)
def cuts(events,dense):
    pending=set();ends=[]
    for i,e in enumerate(events):
        if e.event_type=="tool_call":pending.add(e.call_id)
        if e.event_type=="tool_output":
            pending.remove(e.call_id)
            if not pending:ends.append(i)
    assert not pending and ends
    return ends if dense else sorted(set(old.cuts_for(events)))
def one(tr,rows,dense,tok):
    @lru_cache(maxsize=None)
    def chunks(s):return env.pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    name_map={};oldattrs={};oldedges=set();steps=[]
    for cut in cuts(tr.events,dense):
        prefix=tr.model_copy(update={"events":tr.events[:cut+1],"source_total_steps":cut+1,"source_metadata":None,"final_response":""})
        graph=build_provenance_graph(prefix,content_chunker=chunks)
        ids,g=geometry({"g":graph.model_dump()})
        pool=env.pilot.native.provenance_unit_candidates(graph)
        assert {v.item_id for v in pool}==set(ids)
        for nid in sorted(ids):
            if nid not in name_map:name_map[nid]=len(name_map)
        sizes=Counter(v.source_spans[0].event_id for v in pool)
        attrs={}
        for v in pool:
            md=v.metadata.attrs if hasattr(v.metadata,"attrs") else v.metadata
            attrs[name_map[v.item_id]]=[int(md["node_kind"]=="content.tool_output"),md["token_count"],md["chunk_index"],sizes[v.source_spans[0].event_id]]
        edges={(name_map[a],name_map[b],k) for a,b,k in edges_by_name(ids,g)}
        add=[[u,*v] for u,v in sorted(attrs.items()) if u not in oldattrs or v!=oldattrs[u]]
        queries=[[name_map[n] for n in rr if n in ids] for rr in rows]
        assert all(set(q)==attrs.keys() and len(q)==len(attrs) for q in queries)
        steps.append({"cut":cut,"up":add,"rm":sorted(set(oldattrs)-set(attrs)),"plus":sorted(edges-oldedges),"minus":sorted(oldedges-edges),
                      "dense":queries,"snapshot":hashlib.sha256(json.dumps([sorted(attrs.items()),sorted(edges)],separators=(",",":")).encode()).hexdigest()})
        oldattrs,oldedges=attrs,edges
    return steps
def main():
    parent=W/"graph_memory_round21/incremental_binding/plan.json"
    targets=load(parent)["trajectories"][:48];sel=set(targets);dense=set(targets[:8])
    tok=env.pilot.offsets(env.pilot.Tokenizer.from_file(str(env.pilot.CACHE/"tokenizer.json")))
    locks={v["path"]:v["sha256"] for v in load(env.R18/"isetrace_official/source-lock.json")}
    total=[];sources={};ranks={}
    for i in range(8):
        path=env.RAW/f"trajectories-{i:05d}.jsonl";sources[path.name]=sha(path);assert sources[path.name]==locks["trajectories/"+path.name]
        orig=ref.TR/f"forecasts-main-{i}.json.gz";ranks[orig.name]=sha(orig)
        by=defaultdict(list)
        for o in load(orig):
            if o["t"] in sel:by[o["t"]].append([n["node_id"] for n in o["rr"]])
        for line,obj in env.pilot.stream(path):
            t=obj["session_id"]
            if t not in sel:continue
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            steps=one(tr,by[t],t in dense,tok)
            total.append({"t":t,"source":hashlib.sha256(line).hexdigest(),"dense_schedule":t in dense,"steps":steps})
        print("raw shard",i,"traces",len(total),"states",sum(len(v["steps"]) for v in total),flush=True)
        save(D/f"fixture-{i}.json.gz",[r for r in total if r["t"] in by])
    assert {r["t"] for r in total}==sel and len(total)==48
    save(D/"fixture-lock.json",{"cohort":sha(parent),"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"fixtures.py"),
         "weights":sha(W/"graph_memory_round33/relative_structure/weights.json"),"rank_model":sha(W/"graph_memory_round20/factor_reader/hash64-weights.json"),"raw_shards":sources,"dense":ranks,"files":{f"fixture-{i}.json.gz":sha(D/f"fixture-{i}.json.gz") for i in range(8)}})
if __name__=="__main__":main()
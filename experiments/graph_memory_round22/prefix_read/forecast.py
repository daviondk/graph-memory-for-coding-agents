"""Read only observed source units; compare proper as-of and hindsight topology."""
from collections import defaultdict
import hashlib
import math
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
PREV=HERE.parents[1]/"graph_memory_round21"
sys.path.insert(0,str(PREV/"incremental_binding"))
from predict_readout import ref,geometry,FeedIndex,env,Packed,table,features_in_rank_order,rank_strength,packed_stats,np,save
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
from graph_memory.graphs.provenance import build_provenance_graph


def cuts_for(events):
    steps=[];waiting=0
    for j,e in enumerate(events):
        if e.event_type=="tool_call":waiting+=1
        elif e.event_type=="tool_output":
            waiting-=1
            if not waiting:steps.append(j)
    assert not waiting and steps
    return [steps[math.ceil(len(steps)*k/4)-1] for k in range(1,5)]


def edges_by_name(ids,g):
    names=list(ids)
    assert all(ids[n]==j for j,n in enumerate(names))
    members=defaultdict(list)
    for n,gr in enumerate(g.membership):members[int(gr)].append(names[n])
    pairs={(names[a],names[b],0) for a,b in g.adjacent}
    for a,b,k in g.links:pairs.update((x,y,int(k)) for x in members[a] for y in members[b])
    return pairs


def lookup(tr,rec,ids,g):
    positions={e.call_id:{} for e in tr.tool_calls}
    for j,e in enumerate(tr.events):
        if e.event_type in ("tool_call","tool_output"):positions[e.call_id][e.event_type]=j
    first=np.zeros(len(ids),dtype=int);groups={}
    for n in rec["g"]["nodes"]:
        name=n["node_id"]
        if name not in ids:continue
        m=n["attributes"]["call_id"];i=ids[name]
        is_output=n["kind"]==ref.OUTPUT_CHUNK_NODE
        first[i]=positions[m]["tool_output" if is_output else "tool_call"]
        if is_output:groups[m]=int(g.membership[i])
    return first,groups


def truncate(geometry_all,indices,live,groups):
    ids=np.empty(len(geometry_all.membership),dtype=int);ids.fill(-1);ids[indices]=np.arange(len(indices))
    seen=set(geometry_all.membership[indices])
    lit={(int(ids[a]),int(ids[b])) for a,b in geometry_all.adjacent if ids[a]>=0 and ids[b]>=0}
    edges=[(int(a),int(b),int(k)) for a,b,k in geometry_all.links if a in seen and b in seen]
    fixed=[p for p in edges if p[2]!=2]
    def convert(edgelist):
        return [(groups[a],groups[b],2) for a,b in edgelist if a in groups and b in groups and groups[a] in seen and groups[b] in seen]
    def pack(links):
        return Packed(geometry_all.membership[indices],table(sorted(lit),2),table(sorted(links),3))
    return ids,{"exact":pack(fixed+convert(live.support)), "append":pack(fixed+convert(live.ever)),"final":pack(edges)}


def main():
    pilots=env.load(PREV/"incremental_binding/plan.json")["trajectories"]
    audit=set(pilots[:48]);counts=0;receipt={};seen=set();questions=set()
    idx=ref.graph_index();weights=ref.read(ref.HERE/"weights.json")["typed"]
    trainseal=ref.read(ref.HERE/"prediction-plan.json");prevseal=ref.read(PREV/"incremental_binding/readout-lock.json")
    sources={r["path"]:r["sha256"] for r in ref.read(env.R18/"isetrace_official/source-lock.json")}
    split=ref.read(ref.TR/"split.json.gz")["test"]
    save(HERE/"forecast-plan.json",{"source":ref.sha(HERE/"forecast.py"),"protocol":ref.sha(HERE/"PROTOCOL_RU.md"),
         "split":ref.sha(ref.TR/"split.json.gz"),"full_forecasts":ref.sha(PREV/"incremental_binding/readout-lock.json"),
         "weights":ref.sha(ref.HERE/"weights.json"),"audit":sorted(audit),"pilots":pilots})
    tokenizer=env.pilot.offsets(env.pilot.Tokenizer.from_file(str(env.pilot.CACHE/"tokenizer.json")))
    for shard in range(8):
        key=f"forecasts-main-{shard}.json.gz";assert ref.sha(ref.TR/key)==trainseal["test"][key]
        previous=PREV/f"incremental_binding/readout-{shard}.json.gz";assert ref.sha(previous)==prevseal["forecasts"][previous.name]
        old={r["q"]:r["picks"] for r in ref.read(previous)}
        by=defaultdict(list);rows=[]
        for r in ref.read(ref.TR/key):by[r["t"]].append(r)
        source=env.RAW/f"trajectories-{shard:05d}.jsonl";assert env.pilot.sha(source)==sources["trajectories/"+source.name]
        for rb,obj in env.pilot.stream(source):
            t=obj["session_id"]
            if t not in by:continue
            seen.add(t);fp,h=idx[t];assert ref.sha(fp)==h;rec=ref.read(fp)
            assert hashlib.sha256(rb).hexdigest()==rec["raw_source"]
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            ids,g=geometry(rec);nodelist=list(ids)
            first,groups=lookup(tr,rec,ids,g);cuts=cuts_for(tr.events)
            live=FeedIndex()
            for step,e in enumerate(tr.events):
                live.consume(e)
                if step not in cuts:continue
                indices=np.flatnonzero(first<=step)
                local,states=truncate(g,indices,live,groups)
                if t in audit:
                    prefix=tr.model_copy(update={"events":tr.events[:step+1],"source_metadata":None,"final_response":"","source_total_steps":step+1})
                    author=build_provenance_graph(prefix,content_chunker=lambda s:env.pilot.token_chunks(s,tokenizer=tokenizer,max_tokens=504,overlap_tokens=64))
                    subset_dict={nodelist[i]:j for j,i in enumerate(indices)}
                    pids,pg=geometry({"g":author.model_dump()})
                    assert set(pids)==set(subset_dict) and edges_by_name(pids,pg)==edges_by_name(subset_dict,states["exact"]), (t,step)
                    counts+=1
                for r in by[t]:
                    q=r["q"];rr=r["rr"];questions.add(q)
                    available=[j for j,n in enumerate(rr) if first[ids[n["node_id"]]]<=step]
                    order=np.array([local[ids[rr[j]["node_id"]]] for j in available],dtype=int)
                    assert len(order)==len(indices) and len(order)>0
                    cs=[rr[j]["token_count"] for j in available];strength=rank_strength(order)
                    selections={"dense":[available[j] for j in ref.pack(range(len(order)),cs,False)]}
                    for k,geom in states.items():
                        x=features_in_rank_order(order,packed_stats(geom,strength))
                        rank=np.argsort(-(x@weights["w"]+weights["bias"]),kind="stable")
                        selections[k]=[available[j] for j in ref.pack(rank,cs,False)]
                    if step==cuts[-1]:
                        assert selections["exact"]==selections["final"]==old[q]["exact"] and selections["append"]==old[q]["append"]
                    for percentile,cut in zip((25,50,75,100),cuts):
                        if cut==step:rows.append({"t":t,"q":q,"cut":percentile,"step":step,"pilot":t in pilots,"available":available,"selected":selections})
        out=HERE/f"forecast-{shard}.json.gz";save(out,rows);receipt[out.name]=ref.sha(out)
        print("prefix",shard,len(rows),"native prefix controls",counts,flush=True)
    assert seen=={r["t"] for r in split} and questions=={r["q"] for r in split}
    save(HERE/"forecast-lock.json",{"files":receipt,"queries":len(questions),"trajectories":len(seen),"native_history_checks":counts,
         "plan":ref.sha(HERE/"forecast-plan.json")})

if __name__=="__main__":main()

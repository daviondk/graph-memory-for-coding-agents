"""Reconstruct active data.feeds from the upstream builder after every tool output."""
from oracle import l,D,L,lru_cache,hashlib,json
def main():
    markup=(D/"index.html").read_text(encoding="utf8");data=json.loads(markup.split('<script id="dataset" type="application/json">')[1].split('</script>')[0])
    tok=l.env.pilot.offsets(l.env.pilot.Tokenizer.from_file(str(l.env.pilot.CACHE/"tokenizer.json")))
    records=l.read(D/"source.json")["inputs"];stats={}
    for c in data["cases"]:
        q=c["q"];t=c["history"];sh=records[q]["shard"]
        raw=next(v for _,v in l.env.pilot.stream(l.env.RAW/f"trajectories-{sh:05d}.jsonl") if v["session_id"]==t)
        traj=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(raw),source_revision=l.env.pilot.RAW[1])
        ix={v["hash"]:j for j,v in enumerate(c["nodes"])}
        def addr(s):return ix[hashlib.sha256(s.encode()).hexdigest()[:12]]
        @lru_cache(maxsize=None)
        def chunk(s):return l.env.pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
        previous=set();ever=set();plus=[];minus=[];n=0;total_add=0;total_remove=0
        completed=set();audit={}
        for step,e in enumerate(traj.events,1):
            if e.event_type!="tool_output":continue
            completed.add(e.call_id)
            # The native constructor requires matched calls. Keep all events whose candidate output already exists.
            prefix=tuple(x for x in traj.events[:step] if x.event_type!="tool_call" or x.call_id in completed)
            subset=traj.model_copy(update={"events":prefix,"source_metadata":None,"final_response":"","source_total_steps":step})
            graph=l.parent.build_provenance_graph(subset,content_chunker=chunk);nodes,geom=l.geometry({"g":graph.model_dump()})
            feed={(addr(a),addr(b),2) for a,b,k in l.edges_by_name(nodes,geom) if k==2};n+=1
            plus.extend([*v,step] for v in sorted(feed-previous));minus.extend([*v,step] for v in sorted(previous-feed))
            ever.update(feed);previous=feed
            this=[z for z in c["cuts"].values() if z["step"]==step]
            for z in this:
                assert plus==z["added_events"] and minus==z["removed_events"],(q,step,len(plus),len(minus))
                assert len(ever&set(map(tuple,z["stale"])))==z["stale_visible"]
                cut=next(k for k,v in c["cuts"].items() if v["step"]==step)
                audit[cut]={m:{"count":len(a),"first":a[:60],"sha":hashlib.sha256(json.dumps(a,separators=(",",":")).encode()).hexdigest()} for m,a in (("added_events",plus),("removed_events",minus))}
            if this:total_add+=len(plus);total_remove+=len(minus);plus=[];minus=[]
        assert len(plus)==len(minus)==0
        stats[q]={"cuts":audit,"native_output_prefixes":n,"observed_additions":total_add,"observed_removals":total_remove}
    l.save(D/"event-oracle.json",{"states":stats,"prefixes":sum(v["native_output_prefixes"] for v in stats.values()),"code":l.sha(D/"event_oracle.py"),"source":l.sha(D/"source.json")})
    print({q:s["native_output_prefixes"] for q,s in stats.items()},flush=True)
if __name__=="__main__":main()

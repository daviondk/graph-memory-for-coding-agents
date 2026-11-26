"""Export anonymized topology and graph-independent scores from real ISETrace prefixes."""
import os
for env in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[env]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
from pathlib import Path
from collections import defaultdict
import hashlib,json,sys
D=Path(__file__).resolve().parent;WORK=D.parents[1];LIVE=WORK/"graph_memory_round34/live_reader"
sys.path.insert(0,str(LIVE))
import live as l
h=lambda s:hashlib.sha256(s.encode()).hexdigest()
def hashed_span(z):return [h(z["event_id"]+"\0"+z["json_pointer"])[:16],z["char_start"],z["char_end"]]
def pick():
    vals={(r["q"],r["cut"]):r for r in l.read(LIVE/"outcomes.json.gz")};filters=defaultdict(list);info={}
    for i in range(8):
        for row in l.read(LIVE/f"forecast-{i}.json.gz"):
            if row["cut"]!=50 or row["pilot"]:continue
            q=row["q"];v=vals[q,50];e,a=row["selected"]["exact"][2],row["selected"]["append"][2]
            if not v["eligible"] or set(e)==set(a):continue
            delta=v["arms"]["exact"][0]-v["arms"]["append"][0]
            kind={1:"win",-1:"loss",0:"tie"}[delta];filters[kind].append(q);info[q]=(i,row["t"])
    answers={};ts=set()
    for kind in ("win","loss","tie"):
        q=next(q for q in sorted(filters[kind],key=lambda s:h("R35-live-icde/"+s)) if info[q][1] not in ts)
        i,t=info[q];answers[q]=(i,t,kind);ts.add(t)
    return answers,{k:len(v) for k,v in filters.items()},vals
def main():
    selected,counts,vals=pick();graph,rank,_,patch,_=l.read_models();gold=l.read(l.ref.OFF/"gold-spans.json.gz")
    graph_idx=l.ref.graph_index();cases={};provenance={}
    for q,(i,t,kind) in selected.items():
        src=l.ref.TR/f"forecasts-main-{i}.json.gz";row=next(r for r in l.read(src) if r["q"]==q)
        f=l.read(LIVE/f"forecast-{i}.json.gz");f={r["cut"]:r["selected"] for r in f if r["q"]==q}
        raw=l.env.RAW/f"trajectories-{i:05d}.jsonl"
        rb,obj=next((rb,o) for rb,o in l.env.pilot.stream(raw) if o["session_id"]==t)
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1])
        graphpath,sign=graph_idx[t];rec=l.read(graphpath);assert l.sha(graphpath)==sign and hashlib.sha256(rb).hexdigest()==rec["raw_source"]
        ids,g=l.geometry(rec);first,groups=l.parent.lookup(tr,rec,ids,g);cuts=l.parent.cuts_for(tr.events);feed=l.FeedIndex()
        rr=row["rr"];nid={v["node_id"]:j for j,v in enumerate(rr)};by={u["node_id"]:u for u in rr}
        nodes=[{"hash":h(v["node_id"])[:12],"role":int(v["node_id"].startswith("output-content:")),"tokens":v["token_count"],"spans":[hashed_span(z) for z in v["source_spans"]]} for v in rr]
        assert len({n["hash"] for n in nodes})==len(nodes)
        case={"q":q,"history":t,"kind":kind,"nodes":nodes,"gold":[hashed_span(z) for z in gold[q]],"cuts":{}}
        output_units=defaultdict(list)
        member_to_call={value:k for k,value in groups.items()}
        for k,ix in ids.items():
            if int(g.membership[ix]) in member_to_call:output_units[member_to_call[int(g.membership[ix])]].append((nid[k],int(first[ix])))
        live_feed=set();ever_visible=set();added_events=[];removed_events=[]
        for step,event in enumerate(tr.events):
            feed.consume(event)
            active={(x,y,2) for left,right in feed.support for x,start in output_units[left] if start<=step
                    for y,end in output_units[right] if end<=step}
            added_events.extend([*z,step+1] for z in sorted(active-live_feed))
            removed_events.extend([*z,step+1] for z in sorted(live_feed-active))
            live_feed=active;ever_visible.update(active)
            if step not in cuts:continue
            idx=l.np.flatnonzero(first<=step);_,geoms=l.parent.truncate(g,idx,feed,groups)
            names=[k for j,k in enumerate(ids) if first[j]<=step];local={k:j for j,k in enumerate(names)}
            avail=[j for j,n in enumerate(rr) if n["node_id"] in local]
            perm=l.np.array([local[rr[j]["node_id"]] for j in avail]);r=l.np.arange(1,len(avail)+1)
            feats,cost=l.features(names,geoms["exact"],by);x=feats[perm,:7];c=cost[perm];role=x[:,0]
            sig=l.score(rank,l.np.column_stack([-l.np.log(r),1/r,(len(r)-r)/max(1,len(r)-1)]))
            adj=l.correct(patch,l.np.column_stack([l.np.log1p(r),l.np.log1p(c),role,role*l.np.log1p(c)]))
            base=(x@l.np.array(graph["coef"][:7])+graph["intercept"]+sig+adj).tolist();edges={}
            for m in ("exact","append"):
                pairs=l.edges_by_name(local,geoms[m]);edges[m]={(nid[a],nid[b],v) for a,b,v in pairs}
                features,_=l.features(names,geoms[m],by)
                scores=sig+l.score(graph,features)[perm]+adj;order=l.np.argsort(-scores,kind="stable");read=[avail[j] for j in l.prefix(order,c,2048)]
                for cut,pos in zip((25,50,75,100),cuts):
                    if pos==step:assert read==f[cut][m][2]
            assert edges["exact"]<=edges["append"]
            assert {e for e in edges["exact"] if e[2]==2}==live_feed
            data={"added_events":added_events,"removed_events":removed_events,"stale_visible":len((edges["append"]-edges["exact"])&ever_visible),"step":step+1,"alive":avail,"base":base,"edges":sorted(edges["exact"]),"stale":sorted(edges["append"]-edges["exact"])}
            for cut,pos in zip((25,50,75,100),cuts):
                if pos==step:case["cuts"][str(cut)]=data
            added_events=[];removed_events=[]
        assert len(case["cuts"])==4
        cases[kind]=case;provenance[q]={"shard":i,"raw_record":rec["raw_source"],"graph":sign,"ranking":l.sha(src),"forecast":l.sha(LIVE/f"forecast-{i}.json.gz")}
    summary=l.read(LIVE/"results.json")["panels"]["50.eligible"];cohort=summary["vs"]["append"]["FS2048"]
    payload={"cases":[cases[k] for k in ("win","loss","tie")],"counts":counts,"cohort":{"n":summary["n"],"exact":round(summary["means"]["exact"][0]*summary["n"]),
             "append":round(summary["means"]["append"][0]*summary["n"]),**cohort},"weights":graph["coef"][7:]}
    compact=json.dumps(payload,separators=(",",":"),ensure_ascii=False,allow_nan=False).replace("<","\\u003c")
    (D/"index.html").write_text((D/"template.html").read_text(encoding="utf8").replace("__DATA__",compact),encoding="utf8",newline="\n")
    l.save(D/"source.json",{"program":l.sha(Path(__file__)),"inputs":provenance,"r34":l.sha(LIVE/"manifest.json"),"protocol":l.sha(D/"PROTOCOL_RU.md"),"counts":counts,"html":l.sha(D/"index.html")})
    print([(c["kind"],len(c["nodes"]),len(c["cuts"]["50"]["stale"])) for c in payload["cases"]],flush=True)
if __name__=="__main__":main()

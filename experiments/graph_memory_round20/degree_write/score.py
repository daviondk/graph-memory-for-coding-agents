"""Native interval evaluation for both the persisted state and the BM25 response."""
from policy import D,OLD,input_paths,load,save,sha,gzip,json,sys,defaultdict
from statistics import mean
sys.path.insert(0,str(OLD/"tail_read"));from tail import pilot,independent,compare
def main(stage):
    lock=load(D/(stage+"-seal.json"));assert lock["code"]==sha(D/"policy.py")
    truth=load(OLD/("write_transfer/gold-spans.json.gz" if stage=="dev" else "../graph_memory_round18/isetrace_official/gold-spans.json.gz"))
    arms=defaultdict(dict);activity=[]
    for i,(n,h) in enumerate(sorted(lock["files"].items())):
        assert sha(D/n)==h
        with gzip.open(D/n,"rb") as results,gzip.open(input_paths(stage,i)[0],"rb") as source:
            for a,b in zip(results,source,strict=True):
                forecast,raw=json.loads(a),json.loads(b);ad=raw["addresses"];t=raw["t"];assert t==forecast["t"]
                nodes=[]
                for j,(e,l,r,c,_) in enumerate(raw["blocks"]):
                    eid,ptr=ad[e];sp=pilot.SourceSpan(event_id=eid,json_pointer=ptr,char_start=l,char_end=r)
                    nodes.append(pilot.RankedNodeRecord(node_id=str(j),score=0,token_count=c,source_spans=(sp,)))
                for arm,(arch,qs) in forecast["a"].items():
                    for q,selected in qs.items():
                        assert set(selected)<=set(arch)
                        gold=tuple(pilot.SourceSpan.model_validate(s) for s in truth[q])
                        for title,ids,cap in (("archive",arch,8192),("read",selected,2048)):
                            sub=tuple(nodes[j] for j in ids);paid=sum(s.token_count for s in sub);assert paid<=cap
                            v=pilot.span_metrics_under_token_budget(sub,gold,cap);alt=independent(truth[q],[s.model_dump() for s in sub])
                            assert all(abs(getattr(v,k)-a)<1e-12 for k,a in zip(("coverage","density","full_support"),alt,strict=True))
                            key=title+"/"+arm;assert q not in arms[key];arms[key][q]={"t":t,"tokens":paid,**{k:getattr(v,k) for k in ("coverage","full_support","density","f1")}}
        activity.extend(load(D/f"{stage}-activity-{i}.json.gz"))
    assert all(set(rs)==set(truth) for rs in arms.values())
    summary={k:{"hits":int(sum(v["full_support"] for v in rs.values())),**{a:mean(v[a] for v in rs.values()) for a in ("coverage","full_support","density","tokens")}} for k,rs in arms.items()}
    pairs={title+"/"+a+"-"+b:compare(arms[title+"/"+a],arms[title+"/"+b]) for title in ("archive","read") for a,b in (("live","frozen"),("live","static"),("live","adjacent"),("adjacent","frozen"),("static","frozen"))}
    diag={"trajectories":len(activity),"archives_changed":sum(r["retained_differs"] for r in activity),"updates":sum(r["live_priority_updates"] for r in activity),"mean_peak_live":mean(r["peak_live_blocks"] for r in activity)}
    save(D/(stage+"-outcomes.json.gz"),arms);save(D/(stage+"-results.json"),{"n":len(truth),"summary":summary,"pairs":pairs,"activity":diag});print(stage,{k:v["hits"] for k,v in summary.items()},flush=True)
if __name__=="__main__":main(sys.argv[1])

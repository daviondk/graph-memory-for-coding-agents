"""Check numerical sensitivity to scoring each visible pool with the original dense CPU operator."""
from independent import *
from graph_memory.retrieval.requests import TextCandidate
def run_shard(sh):
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-trained/trained-vectors.sqlite3").as_uri()+"?mode=ro",uri=True)
    assert db.execute("select checkpoint from identity").fetchone()[0]==read(ref.TR/"prediction-plan.json")["weights_sha256"]
    vec=Vectors(db);dense=DenseTaskRetriever(model_name="D:/CodexResearch/x20-isetrace-trained/model",encoder=vec,device="cpu")
    source=read(R22/f"forecast-{sh}.json.gz");old={(r["q"],r["cut"]):r for r in source}
    baseline={(r["q"],r["cut"]):r for r in read(HERE/f"forecast-{sh}.json.gz")}
    raw=env.RAW/f"trajectories-{sh:05d}.jsonl";index=ref.graph_index()
    rows=read(ref.TR/f"forecasts-main-{sh}.json.gz");by=defaultdict(list)
    for r in rows:by[r["t"]].append(r)
    gmodel,rank,meta,patch,mp=read_models();prev_weights=ref.read(ref.HERE/"weights.json")["typed"]
    out=[];identical_scores=0
    for _,obj in env.pilot.stream(raw):
        t=obj["session_id"]
        if t not in by:continue
        vec.cache.clear()
        projection=read(Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")/f"{sh}-{t}.json.gz")
        pool=tuple(TextCandidate.model_validate(v) for v in projection["pool"]);questions=dict(projection["q"])
        changed=[];sample=None
        for r in by[t]:
            q=r["q"];rr=r["rr"];names={v["node_id"]:i for i,v in enumerate(rr)}
            for pct in (25,50,75,100):
                a=old[q,pct]["available"];allowed={rr[j]["node_id"] for j in a};cs=tuple(c for c in pool if c.item_id in allowed)
                prediction=dense.rank(TextRankingRequest(task_id=q,query_text=questions[q],candidates=cs))
                order=[names[z.node_id] for z in prediction];assert set(order)==set(a)
                err=max(abs(z.score-rr[names[z.node_id]]["score"]) for z in prediction);assert err<1e-9
                item={"q":q,"t":t,"cut":pct,"same_dense":order==a,"score_error":err,"selected":{"previous":old[q,pct]["selected"]["exact"],"exact":baseline[q,pct]["selected"]["exact"][2]}}
                out.append(item)
                if a!=order:changed.append((pct,r,order,item))
        if not changed:continue
        tr=parent.adapt_isetrace_record(parent.parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
        fp,h=index[t];assert sha(fp)==h;rec=read(fp);ids,g=geometry(rec)
        first,groups=parent.lookup(tr,rec,ids,g);cuts=parent.cuts_for(tr.events);feed=FeedIndex();bycut=defaultdict(list)
        for pct,r,order,item in changed:bycut[cuts[pct//25-1]].append((r,order,item))
        rrmap={r["node_id"]:r for r in by[t][0]["rr"]}
        for step,e in enumerate(tr.events):
            feed.consume(e)
            if step not in bycut:continue
            idx=np.flatnonzero(first<=step);ids_local,gs=parent.truncate(g,idx,feed,groups)
            visible=[list(ids)[j] for j in idx];locations={n:j for j,n in enumerate(visible)}
            f,cost=features(visible,gs["exact"],rrmap);prior=score(gmodel,f)
            for r,order,item in bycut[step]:
                loc=np.asarray([locations[r["rr"][j]["node_id"]] for j in order]);n=len(loc);rr=np.arange(1,n+1);c=cost[loc];role=f[loc,0];global_ix=np.asarray(order)
                sig=score(rank,np.column_stack([-np.log(rr),1/rr,(n-rr)/max(1,n-1)]))
                new=sig+prior[loc]+correct(patch,np.column_stack([np.log1p(rr),np.log1p(c),role,role*np.log1p(c)]))
                oldx=parent.features_in_rank_order(loc,parent.packed_stats(gs["exact"],parent.rank_strength(loc)))
                previous=oldx@prev_weights["w"]+prev_weights["bias"]
                for m,v in [("exact",new),("previous",previous)]:item["selected"][m]=global_ix[prefix(np.argsort(-v,kind="stable"),c,2048)].tolist() if m=="exact" else global_ix[ref.pack(np.argsort(-v,kind="stable"),c.tolist(),False)].tolist()
    db.close();assert len(out)==len(old);path=HERE/f"native-{sh}.json.gz";save(path,out);return path.name,sha(path)
def assess():
    seal=read(HERE/"native-seal.json");orig={(r["q"],r["cut"]):r for r in read(HERE/"outcomes.json.gz")}
    gold=read(ref.OFF/"gold-spans.json.gz");rows=[]
    for i in range(8):
        p=HERE/f"native-{i}.json.gz";assert sha(p)==seal["predictions"][p.name]
        native=read(p);rr={r["q"]:[RankedNodeRecord.model_validate(k) for k in r["rr"]] for r in read(ref.TR/f"forecasts-main-{i}.json.gz")}
        first={(r["q"],r["cut"]):r for r in read(HERE/f"forecast-{i}.json.gz")}
        prior={(r["q"],r["cut"]):r for r in read(R22/f"forecast-{i}.json.gz")}
        for z in native:
            q=z["q"];key=(q,z["cut"]);r=orig[key];gs=tuple(SourceSpan.model_validate(u) for u in gold[q]);arms={}
            for m,sel in z["selected"].items():
                ranked=tuple(rr[q][j] for j in sel);v=span_metrics_under_token_budget(ranked,gs,2048)
                old=first[key]["selected"]["exact"][2] if m=="exact" else prior[key]["selected"]["exact"]
                arms[m]=[int(v.full_support),v.coverage];arms["changed_"+m]=sel!=old
            rows.append({**{k:r[k] for k in ("q","t","cut","pilot","eligible")},"arms":arms,"same_dense":z["same_dense"],"changed_fs":any(arms[m][0]!=r["arms"][m][0] for m in ("exact","previous")),"error":z["score_error"]})
    import importlib.util
    spec=importlib.util.spec_from_file_location("matched_interval",HERE/"evaluate.py");evaluation=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluation)
    sel=[r for r in rows if r["cut"]==50 and r["eligible"] and not r["pilot"]];assert len(sel)==901
    save(HERE/"native-outcomes.json.gz",rows);save(HERE/"native-results.json",{"n":len(rows),"same_dense":sum(r["same_dense"] for r in rows),"max_error":max(r["error"] for r in rows),"new_graph_changed_prefix":sum(r["arms"]["changed_exact"] for r in rows),"previous_changed_prefix":sum(r["arms"]["changed_previous"] for r in rows),"fs_changed":sum(r["changed_fs"] for r in rows),"eligible_mid":{m:sum(r["arms"][m][0] for r in sel) for m in ("exact","previous")},"contrast":evaluation.pair(sel,"exact","previous",0),"n_mid":len(sel),"seal":sha(HERE/"native-seal.json")})
if __name__=="__main__":
    save(HERE/"native-plan.json",{"method":sha(Path(__file__)),"numeric_protocol":sha(HERE/"NATIVE_NUMERICS_RU.md"),"original":sha(HERE/"seal.json"),"encoder_checkpoint":read(ref.TR/"prediction-plan.json")["weights_sha256"]})
    with ProcessPoolExecutor(2) as ex:out=dict(ex.map(run_shard,range(8)))
    save(HERE/"native-seal.json",{"plan":sha(HERE/"native-plan.json"),"predictions":out});assess()

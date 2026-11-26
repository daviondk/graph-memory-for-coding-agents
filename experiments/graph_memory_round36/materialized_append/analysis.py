from materialize import *
CONTRAST=(("M","L"),("E","M"),("E","L"))
def metrics():
    seal=load(D/"forecast-seal.json");assert seal["plan"]==sha(D/"plan.json")
    hist={(r["q"],r["cut"]):r for r in load(R34/"outcomes.json.gz")};refs=load(l.ref.OFF/"gold-spans.json.gz")
    geom={};rows=[];selected=0
    for i in range(8):
        pg=D/f"graphs-{i}.json.gz";po=D/f"orders-{i}.json.gz";assert sha(pg)==seal["files"][pg.name] and sha(po)==seal["files"][po.name];geom.update(load(pg))
        pool={r["q"]:tuple(l.RankedNodeRecord.model_validate(v) for v in r["rr"]) for r in load(l.ref.TR/f"forecasts-main-{i}.json.gz")}
        for q,t,cut,methods in load(po):
            h=hist[q,cut];assert h["t"]==t;gold=tuple(l.SourceSpan.model_validate(s) for s in refs[q]);nodes=pool[q];summ={};changed={};memo={}
            for m in MODES:
                ix=tuple(methods[m][2]);assert len(set(ix))==len(ix)
                if ix not in memo:
                    seq=tuple(nodes[j] for j in ix);price=sum(n.token_count for n in seq);assert price<=2048
                    score=l.span_metrics_under_token_budget(seq,gold,2048);memo[ix]=[int(score.full_support),score.coverage,price,len(ix)];selected+=1
                summ[m]=memo[ix]
            for a,b in CONTRAST:
                x,y=methods[a][-1],methods[b][-1];changed[a+"-"+b]=[int(x!=y),int(set(x)!=set(y))]
            for m,old in (("E","exact"),("L","append")):
                y=h["arms"][old];assert summ[m][:3]==[y[0],y[1],y[4]]
            g=geom[t]["states"][str(cut)]
            for a,b,n in (("E","M","once_visible"),("M","L","never_visible")):
                if not g[n]:assert methods[a]==methods[b]
            rows.append(dict(q=q,t=t,cut=cut,pilot=h["pilot"],eligible=h["eligible"],arms=summ,changed=changed))
    assert len(geom)==1207 and len(rows)==8000
    p=D/"outcomes.json.gz";put(p,rows);keys=("pu","exact","material","logical","once_visible","never_visible");dist={}
    for cut in CUTS:
        vals=[v["states"][str(cut)] for v in geom.values()];numbers={key:np.array([r[key] for r in vals]) for key in keys}
        dist[cut]={k:dict(total=int(v.sum()),nonzero_t=int((v>0).sum()),quantiles=np.quantile(v,[0,.5,.95,1]).tolist()) for k,v in numbers.items()}
        dist[cut]["both_stale_types_trajectories"]=int(((numbers["once_visible"]>0)&(numbers["never_visible"]>0)).sum())
    rng=np.random.default_rng(36031);groups={}
    for cut in CUTS:
        for panel in ("eligible","nonpilot","all2000"):
            group=[r for r in rows if r["cut"]==cut and (not r["pilot"] or panel=="all2000") and (r["eligible"] or panel!="eligible")]
            ts=sorted({r["t"] for r in group});idx={t:j for j,t in enumerate(ts)};trajectory=np.array([idx[r["t"]] for r in group]);sz=np.bincount(trajectory);comparisons={}
            averages={a:np.asarray([r["arms"][a] for r in group]) for a in MODES}
            for a,b in CONTRAST:
                k=a+"-"+b;delta=averages[a]-averages[b];summed=np.zeros((len(ts),4));np.add.at(summed,trajectory,delta);boot=[]
                for _ in range(100):
                    sample=rng.integers(len(ts),size=(100,len(ts)));mult=np.stack([np.bincount(z,minlength=len(ts)) for z in sample]);boot.append((mult@summed)/(mult@sz)[:,None])
                unit=np.array([100,100,1,1]);ci=np.quantile(np.concatenate(boot),[.025,.975],axis=0)*unit
                comparisons[k]=dict(delta=(delta.mean(0)*unit).tolist(),ci95=ci.tolist(),win=(delta>1e-12).sum(0).tolist(),loss=(delta< -1e-12).sum(0).tolist(),changed=np.array([r["changed"][k] for r in group]).sum(0).tolist())
            query_hist=defaultdict(int)
            for r in group:
                v=geom[r["t"]]["states"][str(cut)];status=str(int(v["once_visible"]>0))+str(int(v["never_visible"]>0));query_hist[status]+=1
            groups[str(cut)+"."+panel]=dict(questions=len(group),trajectories=len(ts),means={k:v.mean(0).tolist() for k,v in averages.items()},FSsuccess={k:int(v[:,0].sum()) for k,v in averages.items()},contrasts=comparisons,
                question_count_by_has_once_then_has_never=dict(query_hist))
    assert groups["50.eligible"]["questions"]==901 and groups["50.nonpilot"]["questions"]==1845
    put(D/"results.json",dict(metrics=["FS2048","Coverage2048","spent_tokens","number_retrieved"],contrast_units=["pp","pp","tokens","nodes"],graph_by_trajectory=dist,cuts=groups,
        relevant_events=sum(v["tool_calls"]+v["tool_outputs"] for v in geom.values()),tool_outputs=sum(v["tool_outputs"] for v in geom.values()),unique_scored=selected,seal=sha(D/"forecast-seal.json"),outcomes=sha(p)))
    print("half",groups["50.eligible"]["FSsuccess"],"edges",dist[50])
if __name__=="__main__":metrics()
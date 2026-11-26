"""Paired comparison of an observed graph against the mean of eight matched draws."""
from experiment import *
from collections import Counter
MET=["FS2048","C2048","tokens"]
def collect():
    seal=load(D/"forecast-seal.json");assert seal["plan"]==sha(D/"plan.json")
    source={(r["q"],r["cut"]):r for r in load(P/"outcomes.json.gz")};refs=load(l.ref.OFF/"gold-spans.json.gz");out={};geom={}
    for sh in range(8):
        ps=D/f"selected-{sh}.json.gz";pa=D/f"edges-{sh}.json.gz";assert sha(ps)==seal["files"][ps.name] and sha(pa)==seal["files"][pa.name]
        pool={r["q"]:tuple(l.RankedNodeRecord.model_validate(n) for n in r["rr"]) for r in load(l.ref.TR/f"forecasts-main-{sh}.json.gz")}
        structs=load(pa);geom.update(structs)
        for q,v in load(ps).items():
            t=v["t"];old=source[q,50];assert old["t"]==t;gold=tuple(l.SourceSpan.model_validate(x) for x in refs[q]);nd=pool[q];memo={};arms={};delta={}
            for n,p in v["picks"].items():
                key=tuple(p)
                if key not in memo:
                    s=tuple(nd[i] for i in key);tok=sum(node.token_count for node in s);assert tok<=2048
                    y=l.span_metrics_under_token_budget(s,gold,2048);memo[key]=[int(y.full_support),y.coverage,tok]
                arms[n]=memo[key];delta[n]=[v["full_sha"][n]!=v["full_sha"]["M"],key!=tuple(v["picks"]["M"]),set(key)!=set(v["picks"]["M"])]
                if n in ("E","M","L"):assert arms[n]==old["arms"][n][:3]
            assert arms["M"]==arms["swap"] and delta["swap"]==[False,False,False]
            out[q]=dict(t=t,eligible=old["eligible"],pilot=old["pilot"],arms=arms,changes=delta)
    assert len(out)==2000 and len(geom)==1207;pp=D/"outcomes.json.gz";put(pp,out);summarize(out,geom,pp)
def summarize(out,geom,pp):
    panels={}
    for panel in ("eligible","nonpilot","all"):
        qs=sorted(k for k,v in out.items() if panel=="all" or (not v["pilot"] and (panel!="eligible" or v["eligible"])))
        ts=sorted({out[k]["t"] for k in qs});ind={t:i for i,t in enumerate(ts)};tr=np.array([ind[out[k]["t"]] for k in qs]);ct=np.bincount(tr)
        exact={n:np.asarray([out[q]["arms"][n] for q in qs]).mean(0).tolist() for n in ("E","M","L","swap")};target=np.asarray([out[q]["arms"]["M"] for q in qs]);conditions={}
        for family,can in (("G","global_choice"),("T","target_choice")):
            names=[family+"_"+s for s in SALTS];random=np.array([[out[q]["arms"][m] for m in names] for q in qs]);diff=target[:,None,:]-random
            means=random.mean(0);change=np.array([[out[q]["changes"][m] for m in names] for q in qs],int);sums=np.zeros((len(ts),len(SALTS),3));np.add.at(sums,tr,diff)
            rng=np.random.default_rng(36042);f=[];c=[];ns=len(SALTS)
            for _ in range(100):
                ix=rng.integers(len(ts),size=(100,len(ts)));n=np.stack([np.bincount(z,minlength=len(ts)) for z in ix])
                res=(n@sums.reshape(len(ts),-1)).reshape(100,ns,3)/(n@ct)[:,None,None]
                f.append(res.mean(1));sidx=rng.integers(ns,size=(100,ns));c.append(res[np.arange(100)[:,None],sidx].mean(1))
            scale=np.array([100,100,1]);ci=lambda a:(np.quantile(np.concatenate(a),[.025,.975],axis=0)*scale).tolist()
            qdiff=diff.mean(1);potential=np.asarray([geom[out[q]["t"]][can] for q in qs]);numbers=diff.mean(0)*scale
            outm=dict(random_mean=random.mean(axis=(0,1)).tolist(),M_minus_random=(diff.mean(axis=(0,1))*scale).tolist(),fixed_ci=ci(f),crossed_ci=ci(c),
                per_salt_mean={s:v.tolist() for s,v in zip(SALTS,means)},per_salt_delta={s:v.tolist() for s,v in zip(SALTS,numbers)},
                mc_seed_sd=numbers.std(0,ddof=1).tolist(),mc_mean_se=(numbers.std(0,ddof=1)/np.sqrt(ns)).tolist(),query_salt_win=(diff>1e-12).sum(axis=(0,1)).tolist(),query_salt_loss=(diff< -1e-12).sum(axis=(0,1)).tolist(),
                question_mean_win=(qdiff>1e-12).sum(0).tolist(),question_mean_loss=(qdiff< -1e-12).sum(0).tolist(),
                queries_changed_in_any_salt=(change.any(1)).sum(0).tolist(),queries_changed_averaged_salt=change.mean(1).sum(0).tolist(),
                possible_redraw_q=int(potential.sum()),possible_redraw_t=len({out[q]["t"] for q in qs if geom[out[q]["t"]][can]}),
                conditional_delta=(diff[potential].mean(axis=(0,1))*scale).tolist())
            conditions[family]=outm
        panels[panel]=dict(q=len(qs),t=len(ts),exact=exact,compared=conditions)
    gsummary={};sel={}
    for family,opt in (("G","global_choice"),("T","target_choice")):
        per_salt={};possible=[z for z in geom.values() if z[opt]]
        for s in SALTS:
            name=family+"_"+s
            intersection=sum(len(set(z["H"])&set(z["draws"][name])) for z in geom.values());den=sum(len(z["H"]) for z in geom.values())
            per_salt[s]=dict(matched_edges=intersection,total_historic=den,different_edge_set_traj=sum(z["H"]!=z["draws"][name] for z in geom.values()),different_degrees_traj=sum(z["degree_sha"][name]!=z["degree_sha"]["M"] for z in geom.values()))
        gsummary[family]=dict(non_degenerate=len(possible),per_salt=per_salt)
    gsummary["swaps"]=dict(trajectories_with_accepted_swap=sum(z["swaps"]>0 for z in geom.values()),total_moves=sum(z["swaps"] for z in geom.values()),final_distinct_graphs=sum(z["swapped"]!=z["H"] for z in geom.values()))
    assert panels["eligible"]["q"]==901
    put(D/"results.json",dict(metrics=MET,delta_units=["pp","pp","tokens"],panels=panels,geometry=gsummary,source=sha(pp),forecast=sha(D/"forecast-seal.json")))
    print("matched",[(f,panels["eligible"]["compared"][f]["M_minus_random"][0],panels["eligible"]["compared"][f]["fixed_ci"]) for f in ("G","T")],flush=True)
if __name__=="__main__":collect()
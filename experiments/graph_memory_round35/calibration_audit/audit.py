"""Independent reconstruction of partition membership, model selection and paired outcomes."""
import itertools,os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from collections import defaultdict,Counter
from inspect_inputs import HERE,SCALE,OFF,sha,get,save,digest
def linehash(values):return digest("\n".join(sorted(values)))
def vals(v):return set(v) if isinstance(v,list) else {v}
def check_source():
    out={}
    for base in [SCALE,HERE.parent/"calibration_transfer"]:
        files=get(base/"manifest.json")["files"]
        assert all(sha(base/f)==h for f,h in files.items())
        out[base.name]={"n":len(files),"manifest":sha(base/"manifest.json")}
    inv=get(SCALE/"train-inventory.json");r=inv["records"];off=get(OFF/"split.json.gz"); rr={s:{v["q"]:v["t"] for v in vs} for s,vs in off.items()}
    assert r.keys()==rr["train"].keys() and all(v["t"]==rr["train"][q] and int(digest("scale-v1|"+v["t"])[:16],16)%5==v["fold"] for q,v in r.items())
    assert all(not(set(rr[a])&set(rr[b])) and not(set(rr[a].values())&set(rr[b].values())) for a,b in itertools.combinations(rr,2))
    folds=get(SCALE/"fold-models.json")["folds"]; summaries={}
    for kk,v in folds.items():
        k=int(kk);held={z["t"] for z in r.values() if z["fold"]==k};g={q for q,z in r.items() if z["prior"] and z["fold"]!=k}; rank={q for q,z in r.items() if z["rank_fit"] and z["fold"]!=k};gt={r[q]["t"] for q in g};rt={r[q]["t"] for q in rank}
        assert not held&(gt|rt) and v["graph_trajectory_sha"]==linehash(gt) and v["rank_query_sha"]==linehash(rank)
        assert [len(g),len(gt),len(rank),len(rt),len(held)]==[v[i] for i in ["graph_questions","graph_t","rank_questions","rank_t","held_t"]]
        summaries[kk]=[len(held),len(g),len(rank)]
    mod=get(SCALE/"models.json"); orig=[q for q in inv["order"] if r[q]["small"]]; a=orig+sorted(set(r)-set(orig),key=lambda q:(digest("scale-add-v1|"+r[q]["t"]),digest("scale-add-v1|"+q)))
    nlabels=np.load(SCALE/"numeric-train.npz")["y"];pidx=0;labs={}
    for q in inv["order"]:
        n=r[q]["n"];labs[q]=int(nlabels[pidx:pidx+n].sum());pidx+=n
    assert pidx==len(nlabels)
    for size,z in mod["panels"].items():
        xs=a[:int(size)];assert linehash(xs)==z["panel_sha"] and len({r[q]["t"] for q in xs})==z["trajectories"]
        assert sum(r[q]["n"] for q in xs)==z["candidates"] and sum(labs[q] for q in xs)==z["labels"]
    selection=get(SCALE/"selection.json")
    assert selection["dev_tuning"] is False and selection["primary"]==["oof_3894","original_R33"]
    for s in ("dev","test"):
        z=get(SCALE/(s+"-seal.json"));assert z["fit"]==sha(SCALE/"models.json") and z["selection"]==sha(SCALE/"selection.json") and z["orders"]==sha(SCALE/(s+"-orders.json.gz"))
    return {"verified":out,"splits":{s:[len(v),len(set(v.values()))] for s,v in rr.items()},"folds":summaries,"panels":mod["panels"],"selection":selection}
def resample(values,clusters):
    labels,ij=np.unique(clusters,return_inverse=True); counts=np.bincount(ij);m=len(counts)
    agg=np.stack([np.bincount(ij,weights=z) for z in values.T]).T
    rng=np.random.default_rng(35035); reps=[]
    for _ in range(100):
        idx=rng.integers(0,m,(100,m));reps.extend(agg[idx].sum(axis=1)/counts[idx].sum(axis=1)[:,None])
    return np.quantile(reps,[.025,.975],axis=0).T.tolist()
def measure(rows,labels):
    n=len(rows); groups={}
    for name,ix in [("seed13",[0]),("transfer4",[1,2,3,4]),("all5",[0,1,2,3,4])]:
        v=rows[:,ix]; means=v.mean(axis=1)*100; d=means[:,0]-means[:,1]; ci=resample(d,labels)
        groups[name]={"new":means[:,0].mean(axis=0).tolist(),"old":means[:,1].mean(axis=0).tolist(),"delta":d.mean(axis=0).tolist(),"ci":ci,
            "better":int((v[:,:,0,0]>v[:,:,1,0]).sum()),"worse":int((v[:,:,0,0]<v[:,:,1,0]).sum()),"hindsight_fs":float(v[:,:,:,0].max(axis=2).mean()*100)}
    return {"q":n,"clusters":len(set(labels)),"g":groups}
def main():
    source=check_source();d=get(HERE/"identities.json.gz");qs,ts=d["q"],d["t"];qsorted={s:sorted(q for q,z in qs.items() if z["s"]==s) for s in ["train","dev","test"]};test=qsorted["test"];rows=[];flags=defaultdict(dict); report={}; states=get(HERE.parent/"calibration_transfer/outcomes.json.gz")
    assert set(test)==set(states)
    for q in test:
        z=states[q];assert z["t"]==qs[q]["t"];rows.append([[z["seeds"][i][m][:3] for m in ("oof_3894","original_R33")] for i in ["13","17","29","37","41"]])
    rows=np.array(rows); labels=[qs[q]["t"] for q in test]
    for f in ["qid","tid",*list(qs[test[0]].keys()),*list(ts[labels[0]].keys())]:
        if f in {"s","t","mode"}:continue
        def lookup(q):
            z=qs[q];return {q} if f=="qid" else {z["t"]} if f=="tid" else vals(z[f] if f in z else ts[z["t"]][f])
        h={s:set().union(*(lookup(q) for q in qq)) for s,qq in qsorted.items()}; prior=h["train"]|h["dev"]
        pair={a+"_"+b:len(h[a]&h[b]) for a,b in itertools.combinations(qsorted,2)}
        for q in test:flags[q][f]=bool(lookup(q)&prior)
        sel=[q for q in test if flags[q][f]];report[f]={"distinct":{s:len(v) for s,v in h.items()},"intersection":pair,"test_seen_q":len(sel),"test_seen_t":len({qs[q]["t"] for q in sel})}
    cand=get(HERE/"candidate-flags.json.gz");assert cand.keys()==set(test)
    for q in test:flags[q].update(cand[q])
    masks={"all":[True]*len(test),"new_full_documents":[not any(flags[q][f] for f in ("query_norm","packet_norm","visible_transcript_norm")) for q in test],
         "new_intent":[not flags[q]["intent_norm"] for q in test],"new_quote":[not flags[q]["gold_norm"] for q in test],"new_intent_quote":[not (flags[q]["intent_norm"] or flags[q]["gold_norm"]) for q in test],"reused_intent":[flags[q]["intent_norm"] for q in test],"reused_quote":[flags[q]["gold_norm"] for q in test],
         "new_gold_units":[not cand[q]["any_gold_unit_seen_in_prior_pool"] for q in test],"new_intent_quote_goldunits":[not (flags[q]["intent_norm"] or flags[q]["gold_norm"] or cand[q]["any_gold_unit_seen_in_prior_pool"]) for q in test],"all_pool_units_new":[not cand[q]["any_pool_text_seen"] for q in test]}
    res={};memo={}
    for k,mask in masks.items():
        v=np.array(mask);key=v.tobytes(); lab=np.array(labels)[v]
        if key not in memo and v.any():memo[key]=measure(rows[v],lab)
        res[k]=memo.get(key,{"q":0})
    parent={t:t for t in labels}; first={}
    def root(t):
        while parent[t]!=t:parent[t]=parent[parent[t]];t=parent[t]
        return t
    for t in sorted(parent):
        for h in ts[t]["intent_norm"]:
            other=first.setdefault(h,t);parent[root(t)]=root(other)
    comps=[root(t) for t in labels];cnt=Counter(root(t) for t in parent);r=measure(rows,comps)
    save(HERE/"audit-results.json",{"source":source,"identities":report,"candidate_audit":get(HERE/"candidate-audit.json"),"subsets":res,"components":{"n":len(cnt),"largest_t":max(cnt.values()),"largest_q":max(Counter(comps).values()),"multi_t":sum(n>1 for n in cnt.values()),"metrics":r},"metrics":["FS2048","Coverage_budget_AUC","FS_budget_AUC"]})
    for k,v in res.items():print(k,v["q"],(v["g"]["transfer4"]["delta"][0],v["g"]["transfer4"]["ci"][0]) if v["q"] else "-",flush=True)
if __name__=="__main__":main()

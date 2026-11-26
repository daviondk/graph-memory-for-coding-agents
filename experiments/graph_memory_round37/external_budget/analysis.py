from threshold import *
import numpy as np, math
def summary(vals):
    return {"n":len(vals),"mean":float(np.mean(vals)),"median":float(np.median(vals))} if vals else {"n":0,"mean":None,"median":None}
def cap(a):return min(a["cost8"] if a["cost8"] is not None else 6144,6144)
def area(a):
    x=a["cost8"];return 0 if x is None else math.log(8192/max(512,min(x,8192)))/math.log(16)
def curve(a):
    return np.asarray(a["budgets"],dtype=float)
def example(q,r,k):
    return {"q":q,"repo":r["repo"],"task":r["task"],"budget":BUD[k],"groups_quota":r["group_quota"],"alt_sizes":r["alt_sizes"],"arms":{m:{a:r["arms"][m][a] for a in ["rank_full","rank8","cost8","cert_eligible_tokens","outside_tokens","group_ranks","alternate_ranks","head"]}|{"success_free_outside":r["arms"][m]["budgets"][k][6],"actual_units":r["arms"][m]["budgets"][k][5],"actual_paid":r["arms"][m]["budgets"][k][4]} for m in METHODS[:2]}}
def main():
    raw=load(D/"thresholds.json.gz");qids=sorted(raw);repos,cl=np.unique([raw[q]["repo"] for q in qids],return_inverse=True);sizes=np.bincount(cl);rng=np.random.default_rng(373713);draw=rng.integers(0,len(repos),(10000,len(repos)));w=np.stack([np.bincount(a,minlength=len(repos)) for a in draw]);weights=w/(w@sizes)[:,None]
    def paired(v):
        x=np.asarray(v,dtype=float);s=np.zeros((len(repos),*x.shape[1:]));np.add.at(s,cl,x);means=(weights@s.reshape(len(repos),-1)).reshape(10000,*x.shape[1:])
        return {"point":x.mean(0).tolist(),"ci":np.quantile(means,[.025,.975],axis=0).tolist()}
    agg={};arr={};meta={}
    for m in METHODS:
        a=[raw[q]["arms"][m] for q in qids];c=np.array([curve(v) for v in a]);arr[m]=c
        agg[m]={"restricted_cost":float(np.mean([cap(v) for v in a])),"log_uniform_complete_pct":float(100*np.mean([area(v) for v in a])),"budget_curve_mean":c.mean(0).tolist(),"finite8":sum(x["cost8"] is not None for x in a),"group_route8":sum(all(k is not None and k<=8 for k in x["group_ranks"]) for x in a),"alt_route8":sum(any(k is not None and k<=8 for k in x["alternate_ranks"]) for x in a),"first_rank_full":summary([x["rank_full"] for x in a if x["rank_full"] is not None]),"no_full_certificate_in_pool":sum(x["rank_full"] is None for x in a),"uncapped8_mean":np.asarray([x["uncapped8"] for x in a]).mean(0).tolist(),"cost_among_finite8":summary([x["cost8"] for x in a if x["cost8"] is not None])}
        # Absolute counts for the different routes, with the exact same token budgets.
        agg[m]["budget_counts"]=[{"mss":int(v[:,0].sum()),"all_groups":int(v[:,2].sum()),"some_alt":int(v[:,3].sum()),"alt_only":int(((v[:,3]==1)&(v[:,2]==0)).sum()),"group_only":int(((v[:,3]==0)&(v[:,2]==1)).sum()),"paid_mean":float(np.mean(v[:,4]))} for v in c.transpose(1,0,2)]
    contrasts={};aa="union_cost"
    for bb in ("dense_state","equal_neg_weights","no_edges"):
        u=[raw[q]["arms"][aa] for q in qids];b=[raw[q]["arms"][bb] for q in qids];d=arr[aa]-arr[bb]
        contrasts[bb]={"token_savings":paired([cap(y)-cap(x) for x,y in zip(u,b)]),"log_uniform_delta_pp":paired([100*(area(x)-area(y)) for x,y in zip(u,b)]),"unlimited8_delta_pp":paired([100*(x["uncapped8"][0]-y["uncapped8"][0]) for x,y in zip(u,b)]),"curve_mss_pp":paired(100*d[:,:,0]),"curve_group_recall_pp":paired(100*d[:,:,1]),"curve_all_groups_pp":paired(100*d[:,:,2]),"curve_free_distractors_pp":paired(100*d[:,:,6]),"wins":(d[:,:,0]>0).sum(0).tolist(),"losses":(d[:,:,0]<0).sum(0).tolist()}
    dec={};breaks={};examples={};sortedq=sorted(qids,key=lambda q:hashlib.sha256(("ser-cost-example/v1/"+q).encode()).hexdigest())
    for k,B in enumerate(BUD):
        z=Counter();actual=[]
        for q in qids:
            old,new=[raw[q]["arms"][m] for m in METHODS[:2]];uo,un=old["budgets"][k],new["budgets"][k]
            if uo[0]==un[0]:continue
            win=un[0]>uo[0];failed=old if win else new;name="win" if win else "loss";reason="rank8" if failed["cost8"] is None else "token";z[name+"_"+reason]+=1
            if failed["budgets"][k][6]:z[name+"_repaired_free_outside"]+=1
            actual.append(q)
        breaks[str(B)]=dict(z)
    for name in ("token_distractor_win","rank8_win"):
        for k in [4,0,1,2,3,5]:
            qs=[]
            for q in sortedq:
                old,new=[raw[q]["arms"][m] for m in METHODS[:2]]
                if not new["budgets"][k][0] or old["budgets"][k][0]:continue
                if name=="token_distractor_win" and old["cost8"] is not None and old["budgets"][k][6]:qs.append(q)
                if name=="rank8_win" and old["cost8"] is None:qs.append(q)
            if qs:
                examples[name]=example(qs[0],raw[qs[0]],k);examples[name]["eligible_examples_at_threshold"]=len(qs);break
        else:examples[name]=None
    du=[];outside=[];inside=[];gain=[];rankdiff=[];both=[];categories={}
    for q in qids:
        old,new=[raw[q]["arms"][m] for m in METHODS[:2]];kind=(old["cost8"] is not None,new["cost8"] is not None);key=("dense_finite" if kind[0] else "dense_censored")+"__"+("union_finite" if kind[1] else "union_censored");categories.setdefault(key,[]).append(cap(old)-cap(new))
        if all(kind):
            both.append(q);du.append(old["cost8"]-new["cost8"]);outside.append(old["outside_tokens"]-new["outside_tokens"]);inside.append(old["cert_eligible_tokens"]-new["cert_eligible_tokens"]);assert du[-1]==outside[-1]+inside[-1]
        assert old["rank_full"] is not None and new["rank_full"] is not None;rankdiff.append(old["rank_full"]-new["rank_full"])
    dec={"both_finite_top8":{"n":len(both),"repos":len({raw[q]["repo"] for q in both}),"cost_savings":summary(du),"outside_savings":summary(outside),"inside_savings":summary(inside),"cheaper_equal_costlier":[sum(x>0 for x in du),sum(x==0 for x in du),sum(x<0 for x in du)]},"full_rank_difference":summary(rankdiff),"capped_saving_by_top8_status":{k:{"n":len(v),"total_tokens":sum(v),"per_all_states":sum(v)/len(qids)} for k,v in categories.items()},"transitions":breaks,"examples":examples}
    needs={"n_groups":dict(Counter(len(r["group_quota"]) for r in raw.values())),"any_quota_above_one":sum(max(r["group_quota"],default=0)>1 for r in raw.values()),"with_alternatives":sum(bool(r["alt_sizes"]) for r in raw.values()),"more_than_one_alternative":sum(len(r["alt_sizes"])>1 for r in raw.values()),"empty_groups":sum(not r["group_quota"] for r in raw.values())}
    res={"split":"test within Cal500","n":len(qids),"repos":len(repos),"budgets":BUD,"curve_cols":["CompleteMSS","GroupRecall","all_groups","any_alternative","read_Qwen_tokens","read_units","MSS_free_outside_certificate"],"arms":agg,"primary_union_minus_controls":contrasts,"mechanism":dec,"certificates":needs,"thresholds":sha(D/"thresholds.json.gz"),"code":sha(D/"analysis.py")};save(D/"results.json",res);print(agg["dense_state"]["restricted_cost"],agg["union_cost"]["restricted_cost"],contrasts["dense_state"],needs)
if __name__=="__main__":main()

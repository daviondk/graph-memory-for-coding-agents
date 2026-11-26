"""Mechanistic controls for the cost-weighted objective on the strong semantic reader."""
from experiment import *
from collections import defaultdict
from serbench import _reference_scorer as sdk
from copy import deepcopy
def modify(items,kind):
    result={}
    for q,row in items.items():
        other=dict(row)
        if kind=="no_edges":
            x=np.array(row["x"]);x[:,2:]=0;other["x"]=x.tolist()
        if kind=="equal_neg_weights":other["wp"]=[1]*len(row["wp"])
        result[q]=other
    return result
def rank(row,model,kind):
    x=np.array(row["x"])
    if kind=="no_edges":x[:,2:]=0
    return np.argsort(-(np.array(row["off"])+(x-model["center"])/model["scale"]@model["weights"]),kind="stable")
def main():
    d=HERE/"strong";data=read(d/"features.json.gz");train={q:r for q,r in data.items() if r["split"]=="train"}
    dev={q:r for q,r in data.items() if r["split"]=="dev"}; labels=split_gold(train.keys()|dev.keys());models={};choices={}
    for k in ("no_edges","equal_neg_weights"):
        t=modify(train,k); av=[]
        for l in (.03,.3):
            mod=optimize(t,labels,"union_cost",l);models[f"{k}_{l}"]=mod
            av.append(np.mean([score(r,rank(r,mod,k),labels[q])[0] for q,r in dev.items()]))
        choices[k]=f"{k}_{(.03,.3)[int(np.argmax(av))]}"
    save(HERE/"ablation-models.json",{"models":models,"choices":choices,"protocol":sha(HERE/"ABLATION_RU.md")})
    pred={q:{k:rank(row,models[name],k).tolist() for k,name in choices.items()} for q,row in data.items() if row["split"]=="test"}
    dst=HERE/"ablation-ranks.json.gz";save(dst,pred);save(HERE/"ablation-seal.json",{"predictions":sha(dst),"models":sha(HERE/"ablation-models.json"),"code":sha(Path(__file__))})
    gold=split_gold(set(pred));old=read(d/"test-outcomes.json.gz");out={}
    for q in pred:
        row=data[q];g=gold[q];y={}
        for k,ix in pred[q].items():
            ix=np.asarray(ix);v=score(row,ix,g);nfit=int(np.sum(np.cumsum(np.array(row["qw"])[ix[:8]])<=6144))
            assert v[0]==sdk.score_prediction([row["ids"][j] for j in ix[:nfit]],g,8)["mss_complete@8"];y[k]=v
        out[q]={"repo":row["repo"],"arms":{**y,**{k:old[q]["arms"][m] for k,m in (("union_cost","union_cost"),("anchor","dense_state"))}}}
    save(HERE/"ablation-outcomes.json.gz",out);groups=defaultdict(list)
    for q,v in out.items():groups[v["repo"]].append(q)
    ordered=sorted(groups);n=len(ordered);s=np.array([len(groups[k]) for k in ordered]); effects={}
    for m in ("anchor","no_edges","equal_neg_weights"):
        arr={q:np.subtract(r["arms"]["union_cost"],r["arms"][m]) for q,r in out.items()}
        g=np.stack([np.sum([arr[q] for q in groups[k]],axis=0) for k in ordered]);rng=np.random.default_rng(34);bs=[]
        for _ in range(100):
            take=rng.integers(n,size=(100,n));bs.extend(g[take].sum(1)/s[take].sum(1)[:,None])
        ds=np.array(list(arr.values()));effects[m]={"delta":ds.mean(0).tolist(),"ci95":np.quantile(bs,[.025,.975],axis=0).tolist(),"wins_losses":[int(np.sum(ds[:,0]>0)),int(np.sum(ds[:,0]<0))]}
    structure={}
    for split,labels1 in (("train",split_gold(train.keys())),("dev",split_gold(dev.keys())),("test",gold)):
        structure[split]={"states":len(labels1),"with_multiple_groups":sum(len(v["required_evidence_groups"])>1 for v in labels1.values()),"with_alternative_set":sum(bool(v["alternative_minimal_sets"]) for v in labels1.values()),"with_multi_id_group":sum(any(len(g["acceptable_evidence_ids"])>1 for g in v["required_evidence_groups"]) for v in labels1.values()),"with_multiplicity":sum(any(g["minimum_required"]>1 for g in v["required_evidence_groups"]) for v in labels1.values())}
    means={m:np.mean([r["arms"][m] for r in out.values()],axis=0).tolist() for m in next(iter(out.values()))["arms"]}
    save(HERE/"ablation.json",{"means":means,"effects_union_minus":effects,"structure":structure,"seal":sha(HERE/"ablation-seal.json")})
    print({m:(v["wins_losses"],v["delta"][0]) for m,v in effects.items()})
if __name__=="__main__":main()

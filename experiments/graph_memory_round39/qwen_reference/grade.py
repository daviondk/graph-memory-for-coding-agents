"""Read native Cal500 labels only after the relevant experiment's prediction seal."""
from panel import *
import numpy as np
from collections import Counter
sys.path.insert(0,str(ROOT.parent/"repo_crossfit"))
from evaluate import score_state
from data import labels

def summarize(outcomes, proposed):
    qs=sorted(outcomes)
    names=sorted(outcomes[qs[0]]["metrics"])
    M=np.array([[outcomes[q]["metrics"][name] for name in names] for q in qs])
    repos,ix=np.unique([outcomes[q]["repo"] for q in qs],return_inverse=True)
    R=np.zeros((len(repos),len(names),4))
    np.add.at(R,ix,M)
    cnt=np.bincount(ix)
    rng=np.random.default_rng(390874)
    draws=rng.integers(len(cnt),size=(10000,len(cnt)))
    W=np.stack([np.bincount(v,minlength=len(cnt)) for v in draws])
    result=dict(states=len(qs),repos=len(cnt),metrics=["MSS@5","MSS@8","MSS@8/2048","MSS@8/6144"],
                successes={m:M[:,j].sum(0).tolist() for j,m in enumerate(names)},contrasts={})
    j=names.index(proposed)
    for k,name in enumerate(names):
        if k==j:
            continue
        diff=M[:,j]-M[:,k]
        samples=W@(R[:,j]-R[:,k])/(W@cnt)[:,None]
        result["contrasts"][name]=dict(micro=diff.mean(0).tolist(),ci95=np.quantile(samples,[.025,.975],axis=0).tolist(),
                                      wins=(diff>0).sum(0).tolist(),losses=(diff<0).sum(0).tolist())
    return result

def main(mode):
    rows=read(R34/"features.json.gz")
    if mode=="blind":
        seal=read(ROOT/"blind-seal.json")
        assert sha(ROOT/"blind-cal-forecasts.json")==seal["calibration"]
        pred=read(ROOT/"blind-cal-forecasts.json")
        assert len(pred)==494
        full=read(ROOT.parent/"repo_crossfit/predictions.json.gz")
        for q,arms in pred.items():
            arms["full_bge_proposed"]=full[q]["proposed"]
        primary="proposed"
    else:
        prefix="gpu-" if mode=="gpu" else ""
        seal=read(ROOT/(prefix+"forecast-seal.json"))
        assert sha(ROOT/(prefix+"qwen-reference.json"))==seal["reference"]
        data=read(ROOT/(prefix+"qwen-reference.json"))
        assert data.keys()==read(ROOT/"panel.json")["states"].keys()
        base=read(R39/"predictions.json.gz")
        static=read(R39/"supervision-predictions.json.gz")
        pred={}
        for q,r in data.items():
            pred[q] = dict(qwen=r["ranks"]["qwen"],qwen_seen=r["ranks"]["qwen_seen"],R39=static[q]["one_distance"],
                           bge=base[q]["dense_state"],union_seen=base[q]["union_unseen"])
        primary="R39"
    gold=labels(set(pred))
    outcomes={}
    for q,arms in pred.items():
        row=rows[q]
        outcomes[q]=dict(repo=row["repo"],metrics=score_state(row,gold[q],arms))
    summary=summarize(outcomes,primary)
    if mode!="blind":
        data=read(ROOT/(prefix+"qwen-reference.json"))
        summary["resources"]=dict(seconds=sum(r["seconds"] for r in data.values()),input_tokens=sum(r["tokens"] for r in data.values()),
                                  truncated=sum(r["truncated"] for r in data.values()),strings=sum(len(r["lengths"]) for r in data.values()),
                                  candidates=sum(len(r["scores"]) for r in data.values()))
        summary["resources"]["tokens_per_second"]=summary["resources"]["input_tokens"]/summary["resources"]["seconds"]
        summary["returnedQwenTokens"]={}
        for mode_name in next(iter(pred.values())):
            sums=[]
            for q,arms in pred.items():
                lookup=dict(zip(rows[q]["ids"],rows[q]["qw"]))
                sums.append([sum(lookup[i] for i in arms[mode_name][:k]) for k in (5,8)])
            summary["returnedQwenTokens"][mode_name]=np.mean(sums,axis=0).tolist()
    write(mode+"-outcomes.json",outcomes)
    write(mode+"-results.json",summary)
    print(mode,summary["successes"])

if __name__=="__main__":
    main(sys.argv[1])

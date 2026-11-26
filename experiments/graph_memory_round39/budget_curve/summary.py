"""Crossed paired bootstrap. All arms share the same resampled trajectories and seed IDs."""
import csv
import os
for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[name]="1"
from time import perf_counter
import numpy as np
from common import D,SEEDS,BUDGETS,ORDERS,SELECTORS,read,save,sha,log

ARM = "R35/graph_dp"
METRICS = ["FullSupport-AUC","Coverage-AUC"]+[f"{metric}@{b}" for b in BUDGETS for metric in ("FullSupport","Coverage","tokens","units")]


def aggregate():
    start = perf_counter()
    arms = [f"{o}/{m}" for o in ORDERS for m in SELECTORS]
    packet_metrics = np.zeros((len(SEEDS),2000,len(arms),len(METRICS)))
    keys, traces, receipts = None,None,{}
    for i,seed in enumerate(SEEDS):
        p = D/f"test-{seed}-outcomes.json.gz"
        receipt = D/f"test-{seed}-score-seal.json"
        assert read(receipt)["outcomes"]==sha(p)
        receipts[str(seed)]=sha(receipt)
        outcomes = read(p)
        if keys is None:
            keys = sorted(outcomes)
            traces = [outcomes[q][0] for q in keys]
        assert keys==sorted(outcomes) and traces==[outcomes[q][0] for q in keys]
        for j,q in enumerate(keys):
            for a,name in enumerate(arms):
                auc,curve = outcomes[q][1][name]
                packet_metrics[i,j,a]=[*auc,*np.ravel(curve)]
    trajectories,labels = np.unique(traces,return_inverse=True)
    n = len(trajectories)
    assert n==1207 and len(keys)==2000
    primary = packet_metrics[:,:,arms.index(ARM)]
    means = packet_metrics.mean(axis=(0,1))
    per_seed = packet_metrics.mean(axis=1)
    controls = [a for a in arms if a!=ARM]
    # Include paired budget endpoints and token costs as well as both primary curve areas.
    use = [i for i,k in enumerate(METRICS) if not k.startswith("units")]
    delta = np.stack([primary-packet_metrics[:,:,arms.index(k)] for k in controls],axis=2)[...,use]
    sizes = np.bincount(labels)
    summed = np.zeros((n,*delta.shape[:1],*delta.shape[2:]))
    np.add.at(summed,labels,delta.transpose(1,0,2,3))
    flat = summed.reshape(n,-1)
    fixed, crossed = [], []
    rng = np.random.default_rng(390039)
    for block in range(100):
        sample = rng.integers(n,size=(100,n))
        counts = np.stack([np.bincount(ix,minlength=n) for ix in sample]).astype(float)
        matrix = (counts@flat).reshape((100,*summed.shape[1:]))/(counts@sizes)[:,None,None,None]
        seeds = rng.integers(len(SEEDS),size=(100,len(SEEDS)))
        fixed.append(matrix.mean(axis=1))
        crossed.append(matrix[np.arange(100)[:,None],seeds].mean(axis=1))
    fixed = np.quantile(np.concatenate(fixed),[.025,.975],axis=0)
    crossed = np.quantile(np.concatenate(crossed),[.025,.975],axis=0)
    by_pair = {}
    for a,name in enumerate(controls):
        original = delta[:,:,a]
        by_pair[name] = dict(delta=original.mean(axis=(0,1)).tolist(),fixed_ci=fixed[:,a].tolist(),
                             crossed_ci=crossed[:,a].tolist(),per_seed=original.mean(axis=1).tolist(),
                             full_auc_wins=np.sum(original[:,:,0]>1e-12,axis=1).tolist(),
                             full_auc_losses=np.sum(original[:,:,0]<-1e-12,axis=1).tolist())
    result = dict(budgets=BUDGETS,seeds=SEEDS,n=2000,trajectories=n,metrics=METRICS,arms=arms,
        means={name:means[a].tolist() for a,name in enumerate(arms)},
        per_seed={str(seed):{name:per_seed[i,a].tolist() for a,name in enumerate(arms)} for i,seed in enumerate(SEEDS)},
        difference_left=ARM,contrast_metrics=[METRICS[i] for i in use],contrasts=by_pair,
        bootstrap_draws=10000,rng=390039,score_seals=receipts)
    save(D/"results.json",result)
    with (D/"curve-points.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream,lineterminator="\n")
        writer.writerow(["input_order","packing","token_budget","full_support","coverage","mean_tokens","mean_nodes"])
        for a,name in enumerate(arms):
            for index,budget in enumerate(BUDGETS):
                point=means[a,2+4*index:6+4*index]
                writer.writerow([*name.split("/"),budget,*[f"{num:.9f}" for num in point]])
    log("summary",elapsed_seconds=round(perf_counter()-start,3),sha256=sha(D/"results.json"))
    for name,v in by_pair.items():
        print(name,round(100*v["delta"][0],4),[round(100*z[0],4) for z in v["crossed_ci"]],flush=True)


if __name__=="__main__":
    aggregate()

"""Grade the immutable packets; bootstrap entire repositories, keeping policies paired."""
from collections import defaultdict
import sys
import numpy as np
from common import *
from predict import charge

METRICS = ("complete", "group", "transfer_tokens", "misses", "packet_tokens", "rank_loss")
PAIRS = (("calibrated","current"),("calibrated","placebo"),("persistence","current"),("innovation","current"),
         ("min_transfer","current"),("min_misses","current"),("min_length","current"),
         ("min_transfer","min_misses"),("min_transfer","min_length"))

def summarize(inputs, packets, outcomes, qs):
    repos = sorted({inputs[q]["repo"] for q in qs})
    names = sorted(packets[qs[0]])
    sums = np.zeros((len(repos), len(names), len(METRICS)))
    sizes = np.zeros(len(repos), dtype=int)
    for q in qs:
        i = repos.index(inputs[q]["repo"])
        sizes[i] += 1
        sums[i] += [outcomes[q][a] for a in names]
    total = sums.sum(0)
    bs = np.random.default_rng(510311).multinomial(len(repos), np.full(len(repos),1/len(repos)),size=20000)
    den = (bs@sizes)[:,None]
    contrasts = {}
    for a,b in PAIRS:
        delta = sums[:,names.index(a)] - sums[:,names.index(b)]
        qs_delta = np.array([np.subtract(outcomes[q][a],outcomes[q][b]) for q in qs])
        contrasts[a+" - "+b] = dict(mean=(delta.sum(0)/len(qs)).tolist(),ci=np.quantile((bs@delta)/den,[.025,.975],axis=0).tolist(),
            macro=(delta/sizes[:,None]).mean(0).tolist(),wins=(qs_delta>1e-12).sum(0).tolist(),losses=(qs_delta< -1e-12).sum(0).tolist(),
            changed=sum(set(packets[q][a])!=set(packets[q][b]) for q in qs),
            repo_net={r:[int(v[0]),int(v[2])] for r,v in zip(repos,delta)})
    return dict(states=len(qs),repos=len(repos),totals={a:total[i].tolist() for i,a in enumerate(names)},pairs=contrasts)

def main():
    assert sha(HERE/"PROTOCOL_RU.md") == PLAN
    seal=read(HERE/"forecast-seal.json")
    assert seal["packets"]==sha(HERE/"packets.json.gz") and seal["inputs"]==sha(HERE/"inputs.json.gz")
    inputs=read(HERE/"inputs.json.gz");packets=read(HERE/"packets.json.gz")
    labels=UPSTREAM/"data/cal500/labels.jsonl.gz"
    with gzip.open(labels,"rt",encoding="utf8") as f:
        gold={r["state_id"]:r for r in map(json.loads,f) if r["state_id"] in inputs}
    sys.path.insert(0,str(UPSTREAM/"src"))
    from serbench import _reference_scorer as native
    truth=read(EXPERIMENTS/"graph_memory_round47/facet_reader/ordinal-judgments.json.gz")
    save("judgments.json.gz",{q:{k:truth[q][k] for k in ("groups","alts")} for q in inputs})
    out={};verified=0;distinct=0
    base_idcg=native.ideal_group_dcg
    for q,z in inputs.items():
        rindex={i:r for r,i in enumerate(z["current"])}
        memo={};state={};best_for_k={}
        def shared(groups,weights,k):
            if k not in best_for_k: best_for_k[k]=base_idcg(groups,weights,k)
            return best_for_k[k]
        native.ideal_group_dcg=shared
        try:
            for a,inds in packets[q].items():
                p=z["parent"]
                previous={inputs[p]["keys"][i] for i in packets[p][a]} if p else set()
                transferred,misses,total=charge(z,inds,previous)
                mss,group=score(inds,truth[q])
                ident=tuple(inds)
                if ident not in memo:
                    memo[ident]=native.score_prediction([z["ids"][i] for i in inds],gold[q],8)
                ref=memo[ident]
                assert ref["mss_complete@8"]==mss and abs(ref["group_recall@8"]-group)<1e-12
                loss=sum(rindex[i] for i in inds)-sum(range(len(inds)))
                state[a]=[mss,group,transferred,misses,total,loss]
                verified+=1
        finally:
            native.ideal_group_dcg=base_idcg
        distinct+=len(memo);out[q]=state
    save("outcomes.json.gz",out)
    reports={}
    for panel in ("dev","outside"):
        qs=[q for q,z in inputs.items() if z["panel"]==panel]
        reports[panel]=summarize(inputs,packets,out,qs)
        reports[panel+"_warm"]=summarize(inputs,packets,out,[q for q in qs if inputs[q]["parent"]])
    save("results.json",dict(panels=reports,metrics=METRICS,official_packets=verified,distinct_official_calls=distinct,
         scorer_sha256=sha(Path(native.__file__)),labels_sha256=sha(labels),outcomes=sha(HERE/"outcomes.json.gz"),
         forecast=sha(HERE/"forecast-seal.json"),judgments=sha(HERE/"judgments.json.gz"),numpy=np.__version__))
    for p in ("outside","outside_warm"):
        r=reports[p]
        print(p,r["states"],r["repos"])
        for a in ("calibrated","placebo","persistence","innovation","min_transfer","min_length","min_misses","current"):
            print(a,round(r["totals"][a][0]),round(r["totals"][a][2]))
        for pair in ("calibrated - current","min_transfer - current","min_transfer - min_length","min_transfer - min_misses"):
            v=r["pairs"][pair];print(pair, [(round(v["mean"][i],4),round(v["ci"][0][i],4),round(v["ci"][1][i],4)) for i in (0,2)])
if __name__=="__main__":
    main()


"""Regrade sealed ordered unit IDs in official source coordinates and compare paired outcomes."""
import argparse
from collections import Counter
import hashlib
import numpy as np
from study import ARMS, BASE, HERE, SEEDS, read, save, sha
from core42 import signed

ROOT = BASE.parents[1]
STREAM = ROOT/"graph_memory_round49/stream_packet"
FUSION = ROOT/"graph_memory_round42/prefix_fusion"
FIX = ROOT/"graph_memory_round43/fixed_trigger"


def key(q):
    return hashlib.sha256(q.encode()).hexdigest()


def panels(mode):
    gold = signed(STREAM, "judgments.json.gz")
    source = signed(STREAM, "input.json.gz")
    seal_name, pred_name = (("forecast-seal.json","predictions.json.gz") if mode == "mid" else
                            ("trigger-seal.json","trigger-predictions.json.gz"))
    assert read(HERE/seal_name)["forecasts"] == sha(HERE/pred_name)
    pred = read(HERE/pred_name)
    assert set(gold) == set(source) == set(pred)
    outcomes = {}
    missing = []
    for shard in range(8):
        if mode == "mid":
            cases = [(q,t,ids) for q,t,n,ids in signed(BASE,f"test-{shard}.json.gz")]
            fused = signed(FUSION,f"packets-{shard}.json.gz")
        else:
            trig = signed(FIX,f"packets-{shard}.json.gz")
            cases = [(q,t,ids) for q,(t,flag,ids,packs) in trig.items() if flag]
            missing += [q for q,(t,flag,ids,packs) in trig.items() if not flag]
        for q,t,visible_list in cases:
            h = key(q)
            t_record = pred[h]
            assert t_record[0] == t
            packs = t_record[-1]
            visible = set(visible_list)
            requirements = gold[h]
            costs = {r[1]:r[2] for r in source[h][1]}
            total = sum(w for w,_ in requirements)
            available = all(visible.intersection(ids) for _,ids in requirements)
            results = {}
            for seed in SEEDS:
                raw = dict(packs[str(seed)])
                if mode == "mid":
                    p = fused[q]["pred"][str(seed)][2]
                    for name, ids in zip(("r35","native","dense","fusion"),p[:4]):
                        raw[name] = [ids,sum(costs[i] for i in ids)]
                else:
                    assert raw["baseline"][0] == trig[q][3][str(seed)]["full"]
                metrics = {}
                for arm,(ids,tokens) in raw.items():
                    chosen = set(ids)
                    assert chosen <= visible and len(chosen) == len(ids)
                    assert sum(costs[i] for i in chosen) == tokens <= 2048
                    covered = sum(w for w,ids in requirements if chosen.intersection(ids))
                    assert total > 0
                    metrics[arm] = [int(covered == total),covered/total,len(chosen),tokens]
                    assert available or not metrics[arm][0]
                results[str(seed)] = metrics
            outcomes[h] = [t,available,results]
    assert len(outcomes) + len(missing) == 2000
    assert all(pred[key(q)][1] is False for q in missing)
    return outcomes,len({pred[key(q)][0] for q in missing})


def summarize(outcomes, mode):
    arms = sorted(next(iter(outcomes.values()))[-1][str(SEEDS[0])])
    report = {}
    for label, cases in (("all",list(outcomes.values())),("available",[v for v in outcomes.values() if v[1]])):
        groups = sorted({v[0] for v in cases})
        mapping = {g:i for i,g in enumerate(groups)}
        a = np.zeros((len(groups),len(SEEDS),len(arms),4))
        n = np.zeros(len(groups))
        counts = Counter()
        for t,_,r in cases:
            i = mapping[t]
            n[i] += 1
            for j,seed in enumerate(SEEDS):
                for k,arm in enumerate(arms):
                    a[i,j,k] += r[str(seed)][arm]
                for arm in arms:
                    counts[(arm,r[str(seed)]["partners"][0]-r[str(seed)][arm][0])] += 1
        mean = a.sum(axis=(0,1))/(len(SEEDS)*len(cases))
        rng = np.random.default_rng(50081)
        blocks = []
        for start in range(0,10000,100):
            tw = rng.multinomial(len(n),np.full(len(n),1/len(n)),size=100)
            sw = rng.multinomial(len(SEEDS),np.full(len(SEEDS),1/len(SEEDS)),size=100)
            tsums = (tw @ a[:,:,:,0].reshape(len(n),-1)).reshape(100,len(SEEDS),len(arms))
            blocks.append(np.einsum("bs,bsa->ba",sw,tsums)/(tw @ n)[:,None]/len(SEEDS))
        bs = np.concatenate(blocks)
        ci = {}
        target = arms.index("partners")
        for j,arm in enumerate(arms):
            delta = 100*(bs[:,target]-bs[:,j])
            ci[arm] = dict(delta_pp=float(100*(mean[target,0]-mean[j,0])),
                           ci95_pp=np.percentile(delta,[2.5,97.5]).tolist(),
                           gains=counts[(arm,1)],losses=counts[(arm,-1)])
        report[label] = dict(questions=len(cases),trajectories=len(n),
            metrics={arm:mean[j].tolist() for j,arm in enumerate(arms)},partners_vs=ci)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode",choices=["mid","trigger"])
    mode = parser.parse_args().mode
    outcomes, n_missing = panels(mode)
    save(HERE/f"{mode}-outcomes.json.gz",outcomes)
    report = summarize(outcomes, mode)
    report["no_trigger_trajectories"] = n_missing
    save(HERE/f"{mode}-results.json",report)
    for group in ("all","available"):
        print(group,report[group]["questions"],report[group]["metrics"]["partners"],
              report[group]["partners_vs"]["baseline"],report[group]["partners_vs"]["permuted"])


"""Generate budget-specific packets from visible ranks, costs and the frozen graph utility."""
import os
import sys
from time import perf_counter
from common import D,GLOBAL,REMAIN,W,SEEDS,BUDGETS,ORDERS,SELECTORS,read,save,sha,log
sys.path.insert(0,str(GLOBAL))
import packet
np = packet.np


def native_ranks(seed):
    result, sources = {}, {}
    for arm in ORDERS[1:]:
        root = packet.base.OFF/f"seed-{seed}"/arm
        receipt = read(root/"forecast-seal.json")
        assert read(root/"checkpoint.json")["sha"] == read(root/"fit.json")["checkpoint"] == receipt["checkpoint"]
        source = str((root/"forecast-seal.json").relative_to(W))
        sources[source] = sha(root/"forecast-seal.json")
        for shard in receipt["receipts"]:
            p = root/shard["file"]
            assert sha(p) == shard["sha"]
            for r in read(p):
                assert arm not in result.setdefault(r["q"],{})
                result[r["q"]][arm] = r["graph"]
    return result, sources


def packs(order, c, utility, solve, budget):
    cumulative = c[order].cumsum()
    k = int(cumulative.searchsorted(budget,side="right"))
    head = order[:k].tolist()
    slack = budget - (int(cumulative[k-1]) if k else 0)
    firstfit = head.copy()
    for i in order[k:]:
        cost = int(c[i])
        if cost <= slack:
            firstfit.append(int(i))
            slack -= cost
    k = int(cumulative.searchsorted(budget//2,side="right"))
    cap = budget - (int(cumulative[k-1]) if k else 0)
    remainder = order[k:]
    candidates = remainder[c[remainder]<=cap]
    picked = candidates[solve(c[candidates],utility[candidates],cap)]
    return [head,firstfit,order[:k].tolist()+picked.tolist()]


def forecast(seed):
    before = perf_counter()
    path = D/f"test-{seed}-packets.json.gz"
    receipt = D/f"test-{seed}-seal.json"
    if receipt.exists():
        assert read(receipt)["packets"]==sha(path)
        log("resume_from_prediction_seal",seed=seed)
        return
    log("prediction_start",seed=seed)
    native,sources = native_ranks(seed)
    selection = read(GLOBAL/"dev-selection.json")
    assert selection["thresholds"]["graph"]==1024 and selection["frozen_models"]==sha(GLOBAL/"models.json")
    models = read(GLOBAL/"models.json")
    assert models["code"]==sha(GLOBAL/"packet.py") and models["shared"]==sha(REMAIN/"reader.py")
    registry,x = packet.projections("test",seed)
    model = models["models"]["graph"]
    utility = np.logaddexp(0,packet.portable(model,x[:,model["cols"]]))
    solve = packet.base.kernel()
    dll = os.getenv("R39_KNAPSACK_DLL","D:/CodexResearch/x20-bench-workspace/tmp/r39-residual-choice.dll")
    from pathlib import Path
    earlier = GLOBAL/f"test-{seed}-pred.json.gz"
    assert sha(earlier)==read(GLOBAL/f"test-{seed}-seal.json")["packet"]
    prev = read(earlier)
    assert set(prev)==set(registry)==set(native)
    result = {}
    for q,(traj,c,order,_,sl) in registry.items():
        assert (c>0).all()
        arms = []
        for name in ORDERS:
            ranked = order if name=="R35" else np.asarray(native[q][name],dtype=int)
            assert np.array_equal(np.sort(ranked),np.arange(len(c)))
            arms.append([packs(ranked,c,utility[sl],solve,b) for b in BUDGETS])
        assert prev[q][0]==traj and arms[0][3][2]==prev[q][1]["graph-dp"] and arms[0][3][1]==prev[q][1]["R35-firstfit"]
        result[q]=[traj,arms]
    save(path,result)
    save(receipt,dict(packets=sha(path),source_forecasts=sources,old_2048=sha(earlier),budget=list(BUDGETS),
        orders=ORDERS,selectors=SELECTORS,dev_selection=sha(GLOBAL/"dev-selection.json"),model=sha(GLOBAL/"models.json"),
        code=sha(D/"predict.py"),common=sha(D/"common.py"),protocol=sha(D/"PROTOCOL_RU.md"),cpp=sha(REMAIN/"choose.cpp"),
        dll=sha(Path(dll)),features=sha(packet.base.FEAT/"test.json.gz"),global_reference_order_matches=len(result),
        exact_2048_packet_checks=2*len(result),questions=len(result)))
    log("prediction_frozen",seed=seed,seconds=round(perf_counter()-before,3),sha256=sha(path))
    print("Frozen",seed,sha(path),flush=True)


if __name__=="__main__":
    for arg in map(int,sys.argv[1:] or SEEDS):
        forecast(arg)

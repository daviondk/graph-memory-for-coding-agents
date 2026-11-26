"""Portable archive verification; native scoring and model caches are optional."""
from statistics import fmean
from common import D,SEEDS,BUDGETS,ORDERS,SELECTORS,read,sha


def main():
    files = read(D/"manifest.json")["files"]
    assert all(sha(D/f)==v for f,v in files.items())
    result = read(D/"results.json")
    ac = read(D/"audit.json")
    assert ac["summary_sha256"]==sha(D/"results.json")
    for seed in SEEDS:
        pp,op=D/f"test-{seed}-packets.json.gz",D/f"test-{seed}-outcomes.json.gz"
        seal,score=[read(D/f"test-{seed}-{s}.json") for s in ("seal","score-seal")]
        assert seal["packets"]==sha(pp) and score["outcomes"]==sha(op)
        assert score["prediction_seal"]==sha(D/f"test-{seed}-seal.json")
        outputs,pred=read(op),read(pp)
        assert outputs.keys()==pred.keys() and len(pred)==2000
        for o,name in enumerate(ORDERS):
            for m,rule in enumerate(SELECTORS):
                arm=name+"/"+rule
                auc_sums=[0.,0.]
                for q,(trace,byarm) in outputs.items():
                    assert trace==pred[q][0]
                    auc,curve=byarm[arm]
                    for j in (0,1):
                        endpoints=[r[j] for r in curve]
                        v=(sum(endpoints)-.5*(endpoints[0]+endpoints[-1]))/5
                        assert abs(v-auc[j])<1e-12
                        auc_sums[j]+=v
                    for i,b in enumerate(BUDGETS):
                        ids=pred[q][1][o][i][m]
                        assert len(ids)==len(set(ids))==curve[i][3] and 0<=curve[i][2]<=b
                for j,total in enumerate(auc_sums):
                    assert abs(total/2000-result["per_seed"][str(seed)][arm][j])<1e-12
    for arm in result["arms"]:
        for i,value in enumerate(result["means"][arm]):
            assert abs(fmean(result["per_seed"][str(s)][arm][i] for s in SEEDS)-value)<1e-8
    print("Verified",len(files),"files, 540000 packets, 180000 two-endpoint AUC values.")


if __name__=="__main__":
    main()

"""Standard-library portable check of all signed per-question rows and pairwise costs."""
from shared import D,SEEDS,BUDGETS,ORDERS,RULES,read,sha


def main():
    files=read(D/"manifest.json")["files"]
    assert all(sha(D/f)==digest for f,digest in files.items())
    results=read(D/"results.json")
    total=0
    for seed in SEEDS:
        pred=read(D/f"test-{seed}-packets.json.gz")
        outcomes=read(D/f"test-{seed}-outcomes.json.gz")
        assert set(pred)==set(outcomes) and len(pred)==2000
        agg={}
        for q,(t,scores) in outcomes.items():
            assert pred[q][0]==t
            for o,order in enumerate(ORDERS):
                costs=[]
                for m,rule in enumerate(RULES):
                    arm=order+"/"+rule
                    auc,curve=scores[arm]
                    for j in (0,1):
                        vals=[row[j] for row in curve]
                        assert abs((sum(vals)-.5*(vals[0]+vals[-1]))/5-auc[j])<1e-12
                    record=[auc[0],curve[3][0],auc[1],curve[3][1],curve[3][2]]
                    sums=agg.setdefault(arm,[0.]*len(record))
                    for j,v in enumerate(record):
                        sums[j]+=v
                    for k,b in enumerate(BUDGETS):
                        ids=pred[q][1][o][k][m]
                        assert len(set(ids))==len(ids)==curve[k][3] and 0<=curve[k][2]<=b
                        total+=1
                    costs.append([v[2] for v in curve])
                assert costs[3]==costs[7]
        for arm,z in agg.items():
            assert max(abs(x/2000-y) for x,y in zip(z,results["per_seed"][str(seed)][arm]))<1e-10
    print("Verified",len(files),"files and",total,"packets")


if __name__=="__main__":
    main()

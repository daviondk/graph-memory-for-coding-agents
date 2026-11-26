import csv
from time import perf_counter
import sys
from shared import D,REMAIN,SEEDS,BUDGETS,ORDERS,RULES,read,save,sha,log
sys.path.insert(0,str(REMAIN))
import intervals
np=intervals.np


def main():
    start=perf_counter()
    metric=["FullSupportAUC","FullSupport2048","CoverageAUC","Coverage2048","tokens2048"]+[f"FullSupport{b}" for b in BUDGETS if b!=2048]
    arms=[o+"/"+r for o in ORDERS for r in RULES]
    matrix={a:np.zeros((len(SEEDS),2000,len(metric))) for a in arms}
    by_budget={a:np.zeros((len(BUDGETS),4)) for a in arms}
    cost_summaries={}
    qs,ts=None,None
    for i,seed in enumerate(SEEDS):
        op=D/f"test-{seed}-outcomes.json.gz"
        assert read(D/f"test-{seed}-score-seal.json")["outcomes"]==sha(op)
        rows=read(op)
        if qs is None:
            qs=sorted(rows)
            ts=[rows[q][0] for q in qs]
        assert sorted(rows)==qs and [rows[q][0] for q in qs]==ts
        for j,q in enumerate(qs):
            for a in arms:
                area,curve=rows[q][1][a]
                matrix[a][i,j]=[area[0],curve[3][0],area[1],curve[3][1],curve[3][2],*[v[0] for k,v in enumerate(curve) if k!=3]]
                by_budget[a]+=curve
        for o in ORDERS:
            pair=np.array([[[u[2],v[2]] for u,v in zip(rows[q][1][o+"/graph_dp"][1],rows[q][1][o+"/graph_density"][1])] for q in qs])
            diff=pair[:,:,0]-pair[:,:,1]
            cost_summaries.setdefault(o,{})[str(seed)]=dict(equal=(diff==0).sum(axis=0).tolist(),
                average_difference=diff.mean(axis=0).tolist(),mean_absolute_difference=np.abs(diff).mean(axis=0).tolist())
    pairs=[]
    for o in ORDERS:
        pairs.extend([(o+"/graph_dp",o+"/"+r) for r in RULES if r!="graph_dp"])
        pairs.append((o+"/graph_dp_equal_spend",o+"/graph_density"))
    result=intervals.summarize(matrix,ts,pairs)
    result["metrics"]=metric
    result["mean_curves"]={a:(x/(len(SEEDS)*len(qs))).tolist() for a,x in by_budget.items()}
    result["actual_token_difference"]=cost_summaries
    result["budgets"]=BUDGETS
    result["score_seals"]={str(s):sha(D/f"test-{s}-score-seal.json") for s in SEEDS}
    save(D/"results.json",result)
    with (D/"curve-points.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.writer(f,lineterminator="\n")
        writer.writerow(["order","policy","budget","full_support","coverage","mean_tokens","mean_nodes"])
        for a,curve in result["mean_curves"].items():
            for b,row in zip(BUDGETS,curve):
                writer.writerow([*a.split("/"),b,*[f"{v:.9f}" for v in row]])
    log("summarized",seconds=round(perf_counter()-start,3),results=sha(D/"results.json"))
    for a,b in pairs:
        v=result["contrasts"][a+" minus "+b]
        print(a,b,[round(100*x,3) for x in v["delta"][:2]],[[round(100*x,3) for x in z[:2]] for z in v["ci95_crossed"]])


if __name__=="__main__":
    main()

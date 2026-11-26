"""Independent numeric oracle for all tail choices on deterministic public question IDs."""
import hashlib
from shared import D,W,GLOBAL,SEEDS,BUDGETS,ORDERS,read,save
import predict as source
np=source.np


def oracle(costs,values,cap,exact):
    best=np.full(cap+1,-np.inf if exact else 0.)
    best[0]=0
    for cost,value in zip(costs,values):
        if cost<=cap:
            np.maximum(best[cost:],best[:-cost]+value,out=best[cost:])
    return best[cap]


def greedy(order,c,head,cap,utility,density):
    tail=order[len(head):]
    sorted_ids=sorted(tail,key=lambda j:-(utility[j]/c[j] if density else utility[j]))
    remaining=cap
    selected=set()
    for j in sorted_ids:
        if c[j]<=remaining:
            selected.add(j)
            remaining-=c[j]
    return head+[j for j in tail if j in selected]


def main():
    maxima,lists,equal,previous=0,0,0,0
    max_error=0.
    models=read(GLOBAL/"models.json")["models"]
    for seed in SEEDS:
        pred=read(D/f"test-{seed}-packets.json.gz")
        native,_=source.native_ranks(seed)
        reg,x=source.packet.projections("test",seed)
        chosen=sorted(pred,key=lambda q:hashlib.sha256(("hybrid-controls-check|"+q).encode()).digest())[:6]
        for q in chosen:
            _,c,_,_,sl=reg[q]
            g,u=[np.logaddexp(0,source.packet.portable(models[name],x[sl][:,models[name]["cols"]])) for name in ("graph","dense")]
            for a,name in enumerate(ORDERS):
                order=native[q][name]
                for bidx,b in enumerate(BUDGETS):
                    rows=pred[q][1][a][bidx]
                    head=[]
                    hcost=0
                    for j in order:
                        if hcost+c[j]>b//2:
                            break
                        hcost+=c[j]
                        head.append(j)
                    cap=b-hcost
                    tail=order[len(head):]
                    assert all(r[:len(head)]==head for r in rows)
                    assert rows[3]==greedy(order,c,head,cap,g,True)
                    assert rows[4]==greedy(order,c,head,cap,g,False)
                    lists+=2
                    rg=np.log1p(1/np.arange(1,len(tail)+1,dtype=float))
                    matches=[(2,g[tail],cap,False),(5,rg,cap,False),(6,u[tail],cap,False),
                             (7,g[tail],sum(c[j] for j in rows[3][len(head):]),True)]
                    loc={j:k for k,j in enumerate(tail)}
                    for rule,vals,capacity,force in matches:
                        sel=[loc[j] for j in rows[rule][len(head):]]
                        got=sum(vals[j] for j in sel)
                        best=oracle(c[tail],vals,capacity,force)
                        max_error=max(max_error,float(abs(got-best)))
                        assert abs(got-best)<1e-9
                        maxima+=1
        baseline=read(D.parent/"budget_curve"/f"test-{seed}-packets.json.gz")
        for q,(t,orders) in pred.items():
            assert t==baseline[q][0]
            cost=reg[q][1]
            for j in range(len(ORDERS)):
                for k,b in enumerate(BUDGETS):
                    rows=orders[j][k]
                    assert rows[:3]==baseline[q][1][j+1][k]
                    previous+=3
                    assert sum(cost[u] for u in rows[3])==sum(cost[u] for u in rows[7])
                    equal+=1
    save(D/"solver-check.json",dict(all_matched_costs=equal,all_previous_lists=previous,
        sampled_optimal_values=maxima,sampled_greedy_lists=lists,sample_questions_per_seed=6,max_absolute_error=max_error))
    print("Matched costs",equal,"previous lists",previous,"independent optima",maxima,"greedy",lists)


if __name__=="__main__":
    main()

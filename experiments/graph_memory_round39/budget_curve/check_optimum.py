"""Independent vector-valued DP over capacities on deterministically selected real questions."""
from hashlib import sha256
import sys
from common import D,GLOBAL,SEEDS,ORDERS,BUDGETS,read,save
sys.path.insert(0,str(GLOBAL))
import packet


def main():
    np=packet.np
    model=read(GLOBAL/"models.json")["models"]["graph"]
    checks=0
    largest_error=0.
    for seed in SEEDS:
        ledger=read(D/f"test-{seed}-packets.json.gz")
        chosen=sorted(ledger,key=lambda q:sha256(("curve-optimum|"+q).encode()).digest())[:4]
        registry,x=packet.projections("test",seed)
        orders={q:{"R35":registry[q][2]} for q in chosen}
        for name in ORDERS[1:]:
            for i in range(8):
                path=packet.base.OFF/f"seed-{seed}"/name/f"picks-{i}.json.gz"
                for r in read(path):
                    if r["q"] in orders:
                        orders[r["q"]][name]=r["graph"]
        for q in chosen:
            _,c,_,_,sl=registry[q]
            u=np.logaddexp(0,packet.portable(model,x[sl][:,model["cols"]]))
            for i,name in enumerate(ORDERS):
                order=orders[q][name]
                for k,b in enumerate(BUDGETS):
                    ids=ledger[q][1][i][k][2]
                    head=[]
                    used=0
                    for j in order:
                        if used+c[j]>b//2:
                            break
                        head.append(j)
                        used+=c[j]
                    assert list(ids[:len(head)])==head
                    available=b-used
                    dp=np.zeros(available+1)
                    for j in order[len(head):]:
                        cost=c[j]
                        if cost<=available:
                            updated=dp[:-cost]+u[j]
                            np.maximum(dp[cost:],updated,out=dp[cost:])
                    selected=ids[len(head):]
                    value=sum(u[j] for j in selected)
                    error=abs(float(value-dp[-1]))
                    assert error<1e-9
                    largest_error=max(largest_error,error)
                    checks+=1
    save(D/"optimum-check.json",dict(deterministic_questions_per_seed=4,seeds=SEEDS,checks=checks,
        max_absolute_error=largest_error,question_selection="four smallest SHA256(curve-optimum|question_id)"))
    print("Independent optimal values:",checks,largest_error)


if __name__=="__main__":
    main()

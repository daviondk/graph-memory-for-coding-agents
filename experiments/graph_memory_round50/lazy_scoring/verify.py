from benchmark import D,BASE,sha,read,SEEDS,Plans,arrays,PROTOCOL
from analyze import summaries
if __name__=="__main__":
    source=read(D/"run-seal.json")
    assert source["matched"]==sha(BASE/"manifest.json") and source["protocol"]==PROTOCOL
    assert source["code"]==sha(D/"benchmark.py") and source["compiler"]==sha(D/"compiler.json")
    assert read(D/"compiler.json")["binary"]==sha(D/"scoring.dll")
    assert summaries()==read(D/"results.json")
    seed=SEEDS[0];plans=Plans();pool=read(BASE/"pool.json.gz")
    ranks=read(BASE/f"ranks-{seed}.json.gz");ref=read(BASE/f"archive-{seed}.json.gz")
    checks=0
    for q,r in sorted(pool.items())[::17]:
        for cp in (0,1):
            d,*orders=ranks[q]
            p=arrays(dict(z=r["x"],offset=r["o"],costs=r["c"],dense=d,order=orders[cp],seed=seed))
            for m in range(4):
                assert plans.run(p,m)[0]==ref[q][cp][0];checks+=1
    print("Paired intervals from all 240,000 timed executions verified.",checks,"fresh packet checks.")


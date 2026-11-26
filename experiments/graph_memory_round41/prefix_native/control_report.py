from collections import Counter,defaultdict
from shared import D,W,OFF,SEEDS,ARMS,read,save,sha,pack


def main():
    summary=defaultdict(Counter)
    branches=read(D/"forecast-seal.json")
    for i in range(8):
        p=D/f"forecast-{i}.json.gz"
        assert sha(p)==branches["shards"][str(i)]
        rows=read(p)
        costs={r["q"]:[n["token_count"] for n in r["rr"]] for r in read(W/"graph_memory_round19/trained_rank"/f"forecasts-main-{i}.json.gz")}
        for seed in SEEDS:
            for arm in ARMS:
                sh=OFF/f"seed-{seed}"/arm/f"picks-{i}.json.gz"
                assert sha(sh)==next(v["sha"] for v in read(sh.parent/"forecast-seal.json")["receipts"] if v["file"]==sh.name)
                hist={r["q"]:r["graph"] for r in read(sh)}
                for q,t,cut,orders in rows:
                    o=orders[f"{seed}/{arm}"]
                    ids=set(o)
                    final=[j for j in hist[q] if j in ids]
                    for strict in (True,False):
                        a,b=pack(o,costs[q],strict),pack(final,costs[q],strict)
                        for tag in (arm,"both"):
                            c=summary[f"{tag}/{cut}/"+("strict" if strict else "firstfit")]
                            c.update(dict(records=1,ordered=int(a==b),same_set=int(set(a)==set(b))))
    save(D/"control-report.json",dict(groups=summary,ranks=sha(D/"forecast-seal.json")))


if __name__=="__main__":
    main()

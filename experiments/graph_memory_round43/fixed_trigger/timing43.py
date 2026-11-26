"""Describe the new stopping time against the previous fraction only after sealing."""
from collections import Counter
from io43 import D,R41,OFF,read,save,sha


def main():
    sealed=read(D/"forecast-seal.json")
    qcount=Counter(v["t"] for v in read(OFF/"split.json.gz")["test"])
    categories={"trajectories":Counter(),"questions":Counter()}
    calls=Counter();lengths=Counter()
    for i in range(8):
        fp=D/f"traces-{i}.json.gz";assert sha(fp)==sealed["outputs"][str(i)][1]
        old={t:step for t,pct,step,n,e,h in read(R41/f"forecast-{i}-seal.json")["traces"] if pct==50}
        for t,fired,k,ncall,nmsg,ne,nn,h in read(fp):
            if fired:
                time=ne-1
                category="earlier" if time<old[t] else "later" if time>old[t] else "equal"
                calls[ncall]+=1;lengths[nmsg]+=1
            else:category="not_fired"
            categories["trajectories"][category]+=1
            categories["questions"][category]+=qcount[t]
    save(D/"timing.json",dict(categories=categories,actual_calls_per_fired_trajectory=calls,
         consumed_messages_per_fired_trajectory=lengths,seal=sha(D/"forecast-seal.json")))
    print(categories)


if __name__=="__main__":main()

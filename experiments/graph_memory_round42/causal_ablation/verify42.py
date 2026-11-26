from collections import Counter
import hashlib
import numpy as np
from core42 import D,W,CAUSAL,R41,OFF,SEEDS,read,sha


def main():
    manifest=read(D/"manifest.json")["files"]
    assert manifest=={p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}
    seal=read(D/"forecast-seal.json");fit=read(D/"models.json");obs={v["q"]:v for v in read(D/"scores.json.gz")}
    assert len(obs)==2000 and sha(D/"scores.json.gz")==read(D/"grade-seal.json")["scores"]
    assert sha(D/"models.json")==seal["models"] and fit["protocol"]==sha(D/"registration.json")
    assert sha(D/"METHOD_RU.md")==fit["method"]
    assert sha(D/"PROTOCOL_RU.md")==read(D/"registration.json")["protocol"]
    panel=set(sorted(obs,key=lambda q:hashlib.sha256(("r42-verify|"+q).encode()).digest())[:16])
    source_labels=read(D/"train-labels.json.gz")
    assert sha(D/"train-labels.json.gz")==read(D/"train-label-seal.json")["labels"]
    audit=0;lists=0
    for sh in range(8):
        with np.load(D/f"train-{sh}.npz") as aa:
            offset=0;y=aa["labels"]
            for tq,t,n,_ in read(D/f"train-{sh}.json.gz"):
                block=y[offset:offset+n].tobytes();offset+=n
                assert [t,n,sum(block),hashlib.sha256(block).hexdigest()]==source_labels.pop(tq)
            assert offset==len(y)
        fore=D/f"packets-{sh}.json.gz";assert sha(fore)==seal["packets"][str(sh)]
        pred=read(fore)
        ref={r["q"]:[n["token_count"] for n in r["rr"]] for r in read(W/"graph_memory_round19/trained_rank"/f"forecasts-main-{sh}.json.gz")}
        avail={q:set(ids) for q,t,cut,step,ids,*rest in read(CAUSAL/f"state-{sh}.json.gz") if cut==50}
        table=D/f"test-{sh}.npz";records=D/f"test-{sh}.json.gz"
        assert [sha(records),sha(table)]==read(D/f"features-{sh}-seal.json")["rows"]["test"]
        with np.load(table) as a:
            m,e=a["meta"],a["edge"];start=0
            sems={s:a[f"sem{s}"] for s in SEEDS}
            for q,t,n,ids in read(records):
                indices=set(ids);assert len(indices)==n and avail[q]==indices and t==obs[q]["t"]==pred[q][0]
                for seed in SEEDS:
                    s=str(seed);rules=pred[q][1][s]
                    for name,packet in rules.items():
                        assert len(packet)==len(set(packet)) and set(packet)<=indices
                        assert sum(ref[q][j] for j in packet)==obs[q]["arms"][s][name][2]<=2048
                        lists+=1
                    if q not in panel:continue
                    sem=sems[seed]
                    for arm in ("rich","full"):
                        model=fit["models"][arm]["hgb"]
                        ranks=[]
                        for j,item in enumerate(ids):
                            nr=start+j
                            feat=[*sem[nr],*m[nr]]
                            if arm=="full":feat.extend(e[nr])
                            score=model["bias"]
                            for tree in model["trees"]:
                                node=0
                                while tree[node][2]!=tree[node][3]:
                                    col,threshold,left,right,v=tree[node]
                                    node=left if feat[col]<=threshold else right
                                score+=tree[node][4]
                            ranks.append((-score,sem[nr,0],item))
                        remaining=2048;chosen=[]
                        for _,_,item in sorted(ranks):
                            if ref[q][item]<=remaining:
                                chosen.append(item);remaining-=ref[q][item]
                        assert chosen==rules[f"hgb/{arm}"]
                        audit+=1
                start+=n
            assert start==len(m)
    assert audit==160 and not source_labels
    primary=[v for v in obs.values() if not v["pilot"] and v["eligible"]]
    assert len(primary)==901 and len({v["t"] for v in primary})==657
    m=read(D/"results.json")["groups"]["primary"]
    for pair in m["paired"]:
        delta=sum(v["arms"][str(s)][pair["left"]][0]-v["arms"][str(s)][pair["right"]][0] for v in primary for s in SEEDS)
        assert abs(delta/(len(primary)*len(SEEDS))-pair["mean"][0])<1e-12
    print("budgets and membership",lists,"independent scalar tree forecasts",audit,"paired contrasts",len(m["paired"]))


if __name__=="__main__":main()

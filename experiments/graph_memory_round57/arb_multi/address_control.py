"""Post-hoc budget audit: all five returned addresses must be new for every method."""
from statistics import fmean
import numpy as np
from predict import HERE,OLD,read,rowsplit,save
from grade import metrics

def main():
    original=read(HERE/"ranks.json.gz");gold=read(OLD/"ground-truth.json.gz")
    record={};changed={}
    for q,case in rowsplit("code2test"):
        r=original[q];paths=case["paths"];ix=case["ix"];blocked=set(r["seeds"])
        ranks=r["ranks"].copy()
        static=case["mats"]["static"][:,[0,1,3,4,6]].sum(1)
        for method,history in (("base",[]),("linear",r["graph"]),("pair",r["graph_pair"])):
            scores=static.copy()
            for k,p in enumerate(history[:20],1):scores[ix[p]]+=11/(10+k)
            sorted_ids=np.argsort(-scores,kind="stable")
            assert [paths[i] for i in sorted_ids[:5]]==ranks[method]
            ranks[method]=[paths[i] for i in sorted_ids if paths[i] not in blocked][:5]
            if ranks[method]!=r["ranks"][method]:changed.setdefault(q,{})[method]=ranks[method]
        assert all(len(z)==len(set(z))==5 and not blocked.intersection(z) for z in ranks.values())
        record[q]={m:metrics(rank,gold[q]) for m,rank in ranks.items()}
    out={"changed_queries":changed,"means":{m:list(map(fmean,zip(*(rs[m] for rs in record.values()))))
                  for m in next(iter(record.values()))}}
    save(HERE/"address-control.json",out);print(len(changed),out["means"])
if __name__=="__main__":main()

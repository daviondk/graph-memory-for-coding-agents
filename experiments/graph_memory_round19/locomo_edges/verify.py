"""Independent rank-sum ROC-AUC and group-budget recall, using archived scalar scores."""
import collections
import gzip
import hashlib
import itertools
import json
import math
import statistics
from pathlib import Path
D=Path(__file__).resolve().parent
def data(name):
    b=(D/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if (D/"MANIFEST_SHA256.json").exists():
        assert all(sha(D/f)==h for f,h in data("MANIFEST_SHA256.json").items())
    inp=data("input-lock.json");seal=data("forecast-lock.json")
    assert inp["code"]==sha(D/"study.py") and inp["protocol"]==sha(D/"PROTOCOL_RU.md")
    assert seal["input"]==sha(D/"input-lock.json") and seal["forecast"]==sha(D/"forecasts.json.gz")
    truth={(g,k):y for g,k,y in data("labels.json.gz")}
    groups=collections.defaultdict(list); res=data("results.json")
    for r in data("forecasts.json.gz"):
        groups[r["group"]].append((r["key"],truth[r["group"],r["key"]],r["score"]))
    assert len(groups)==10 and len(truth)==sum(map(len,groups.values()))==5882
    ext=data("ablation-results.json")
    assert ext["code"]==sha(D/"ablate.py") and ext["predictions"]==sha(D/"ablation-forecasts.json.gz")
    assert ext["protocol"]==sha(D/"ABLATION_RU.md") and ext["base"]==sha(D/"forecast-lock.json")
    extra={(r["group"],r["key"]):r["score"] for r in data("ablation-forecasts.json.gz")}
    assert set(extra)==set(truth)
    for g,records in groups.items():
        for key,_,s in records:s.update(extra[g,key])
    res["methods"].update(ext["methods"])
    for gr,rows in groups.items():
        pos=sum(x[1] for x in rows)
        for method,v in res["methods"].items():
            ascend=sorted(rows,key=lambda x:x[2][method]); negatives=0; pairs=0
            for _,batch in itertools.groupby(ascend,key=lambda x:x[2][method]):
                batch=list(batch); p=sum(x[1] for x in batch); n=len(batch)-p
                pairs+=p*(negatives+0.5*n); negatives+=n
            expected=v["by"][gr]
            assert math.isclose(pairs/(pos*negatives),expected["auc"],abs_tol=1e-12)
            ranks=list(reversed(ascend))
            for b in (0.1,0.2,0.4):
                k=math.ceil(len(rows)*b)
                assert ranks[k-1][2][method]!=ranks[k][2][method], "Tie at budget cut"
                val=sum(x[1] for x in ranks[:k])/pos
                assert math.isclose(val,expected["recall_"+str(b)],abs_tol=1e-12)
    for m,r in res["methods"].items():
        for k,avg in r["macro"].items():
            assert math.isclose(avg,statistics.mean(v[k] for v in r["by"].values()),abs_tol=1e-12)
    for baseline,contrasts in res["contrasts"].items():
        for key,v in contrasts.items():
            d=[res["methods"]["edge"]["by"][g][key]-res["methods"][baseline]["by"][g][key] for g in sorted(groups)]
            assert d==v["individual"]
            val=sum(abs(sum(i*j for i,j in zip(s,d)))>=abs(sum(d))-1e-12
                    for s in itertools.product((-1,1),repeat=10))/1024
            assert abs(val-v["signflip_p"])<1e-12
    print("Verified 240 group-level metrics, all macro means, and eight sign-flip comparisons.")
if __name__=="__main__":main()


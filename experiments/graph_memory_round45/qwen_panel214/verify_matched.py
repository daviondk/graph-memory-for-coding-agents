"""Standard-library numeric check of all three-field/nine-field lexical retrieval rankings."""
from verify import get,sha
from math import fsum,isclose
def main():
    m=get("matched-weights.json");p=get("matched-predictions.json.gz");s=get("matched-seal.json");rows=get("matched-numeric.json.gz")
    assert s["forecasts"]==sha("matched-predictions.json.gz") and s["weights"]==sha("matched-weights.json")
    assert set(p)==set(rows) and len(rows)==214
    for q,row in rows.items():
        ids=row["ids"];seen=row["seen"];assert len(set(ids))==len(seen)==len(ids)
        for typ,rec in row["values"].items():
            d=m[typ];w=d["coef"];bias=d["intercept"][0];stored=rec["scores"];index=range(len(ids))
            for arr,z in zip(rec["x"],stored,strict=True):
                est=bias+fsum((x-mean)/scale*c for x,mean,scale,c in zip(arr,d["mean"],d["scale"],w,strict=True))
                assert isclose(est,z,rel_tol=1e-10,abs_tol=1e-10)
            for prefix,score in (("lr",stored),("bm",[x[0] for x in rec["x"]])):
                for suffix in ("","_seen"):
                    rank=sorted(index,key=lambda i:(seen[i] if suffix else 0,-score[i],ids[i]))
                    assert [ids[i] for i in rank[:8]]==p[q][prefix+typ+suffix]
    print("Verified 1,712 lexical policy-state rankings and all stored logistic scores.")
if __name__=="__main__":main()

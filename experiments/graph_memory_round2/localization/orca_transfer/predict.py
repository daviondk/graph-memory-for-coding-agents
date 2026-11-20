"""Apply pre-fitted, held-out-repository coefficients to the fresh baseline output."""
import gzip,hashlib,json,sys
from pathlib import Path
D=Path(__file__).resolve().parent;R=D.parent
sys.path.insert(0,str(R/"grounding"))
from features import summarize
def main():
    inputs=json.loads(gzip.decompress((D/"inputs.json.gz").read_bytes()))
    coef=json.loads(gzip.decompress((R/"grounding/coefficients.json.gz").read_bytes()))
    lock=json.loads((D/"design_lock.json").read_bytes())["hashes"]
    assert hashlib.sha256((R/"grounding/coefficients.json.gz").read_bytes()).hexdigest()==lock["coefficients.json.gz"]
    pred=[]
    for i in inputs:
        f=summarize(i);r={}
        for setting in ["loc_loro","river_loro"]:
            ranks={"native":i["paths"]}
            for arm in ["flat","decl","graph","placebo"]:
                a=coef[setting+"|"+i["repo"]+"|all|"+arm]["weights"]
                scores=[sum(v[k]*val for k,val in a.items()) for v in f["features"]]
                ix=range(len(scores)) if i["excluded"] else sorted(range(len(scores)),key=lambda n:(-scores[n],n))
                ranks[arm]=[i["paths"][j] for j in ix]
            r[setting]=ranks
        pred.append({"id":i["id"],"repo":i["repo"],"source":"orca","pred":r,"n_ast":f["n_ast"],"n_blob":f["n_blobs"]})
    (D/"pred.json").write_text(json.dumps(pred,sort_keys=True),encoding="utf8")
    (D/"decision_lock.json").write_text(json.dumps({k:hashlib.sha256((D/k).read_bytes()).hexdigest() for k in ["design_lock.json","pred.json"]},indent=2),encoding="utf8")
if __name__=="__main__":main()


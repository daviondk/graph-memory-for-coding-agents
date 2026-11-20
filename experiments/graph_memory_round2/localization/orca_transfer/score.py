"""Score the sealed OrcaLoca reranking against actual patch paths, plus both release labels."""
import hashlib,json,sys
from pathlib import Path
D=Path(__file__).resolve().parent;R=D.parent
sys.path.insert(0,str(R/"grounding"))
import model
def main():
    for k,v in json.loads((D/"decision_lock.json").read_bytes()).items():assert hashlib.sha256((D/k).read_bytes()).hexdigest()==v
    lab=json.loads((R/"grounding/labels.json").read_bytes())["river"]
    pred=json.loads((D/"pred.json").read_bytes());res={};outfile=[]
    for mode in ["loc_loro","river_loro"]:
        arr=[]
        for r in pred:
            ps=r["pred"][mode];g=lab[r["id"]]
            arms={a:{label:{"hit":int(bool(ls) and ls[0] in paths)} for label,paths in g.items()} for a,ls in ps.items()}
            arr.append(dict(id=r["id"],repo=r["repo"],arms=arms,mode=mode,oracle=int(bool(set(ps["native"])&set(g["patch"])))))
        n=len(arr);outfile.extend(arr)
        counts={a:{label:sum(x["arms"][a][label]["hit"] for x in arr) for label in ["patch","any","single"]} for a in arr[0]["arms"]}
        effect={b:model.stats(arr,"graph",b,"patch") for b in ["native","flat","decl","placebo"]}
        res[mode]=dict(n=n,repos=len({r["repo"] for r in arr}),ceiling=sum(r["oracle"] for r in arr),top1=counts,effect=effect)
    (D/"rows_scored.json").write_text(json.dumps(outfile,sort_keys=True),encoding="utf8")
    (D/"results.json").write_text(json.dumps(res,indent=2),encoding="utf8")
    for m,s in res.items():print(m,s["n"],s["repos"],s["ceiling"],s["top1"],[(m,e["w"],e["l"],e["ci"]) for m,e in s["effect"].items()])
if __name__=="__main__":main()


"""Compare sealed real-library outputs with the pre-existing predictions and the next observed view."""
import gzip,hashlib,json,statistics
from collections import defaultdict
from pathlib import Path
D=Path(__file__).resolve().parent
SOURCE=D.parent/"code_visibility"
def read(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    seal=read(D/"prediction-seal.json")
    forecasts=read(D/"predictions.json.gz")
    assert seal["output_sha256"]==sha(D/"predictions.json.gz")
    baseline={r["q"]:r for r in read(SOURCE/"predictions.json.gz")}
    next_views=read(SOURCE/"observations.json.gz")
    assert set(baseline)==set(forecasts)==set(next_views)
    metrics=defaultdict(lambda:dict(episodes=0,issue_scores=defaultdict(list),right=0,wrong=0,equal=0,facts=0))
    different=[]
    for q,ref in baseline.items():
        retrieved=forecasts[q]
        group=metrics[ref["cohort"]+"_"+ref["window"]]
        target=dict(next_views[q]["observed"])
        group["episodes"]+=1
        group["facts"]+=len(retrieved)
        group["equal"]+=int(retrieved==ref["mem"]["T"])
        if retrieved!=ref["mem"]["T"]:
            different.append(q)
        correct=sum(target.get(i)==h for i,h in retrieved)
        wrong=sum(i in target and target[i]!=h for i,h in retrieved)
        group["right"]+=correct
        group["wrong"]+=wrong
        group["issue_scores"][ref["issue"]].append((correct,len(target)))
    for label,g in metrics.items():
        labels=g.pop("issue_scores")
        g["issues"]=len(labels)
        g["coverage_issue_macro"]=statistics.mean(sum(a for a,b in x)/sum(b for a,b in x) for x in labels.values())
        reference=read(SOURCE/"results.json")["groups"][label]["methods"]["T"]
        assert abs(g["coverage_issue_macro"]-reference["coverage"])<1e-12
    out=dict(groups=metrics,mismatches=different,episodes=len(baseline),seal=sha(D/"prediction-seal.json"))
    (D/"results.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(out["episodes"],len(different),dict(metrics))
if __name__=="__main__":
    main()


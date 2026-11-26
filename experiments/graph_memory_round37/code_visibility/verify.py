"""Independent standard library reconstruction of primary scores from sealed forecasts."""
from pathlib import Path
import json,gzip,hashlib,statistics,collections,math
D=Path(__file__).resolve().parent
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    x=load(D/"prediction-seal.json");s=load(D/"source-seal.json")
    assert x["predictions"]==sha(D/"predictions.json.gz") and x["observations"]==sha(D/"observations.json.gz")
    assert s["code"]==sha(D/"project.py") and x["code"]==sha(D/"predict.py") and s["projection"]==sha(D/"events.json.gz")
    preds=load(D/"predictions.json.gz");gold=load(D/"observations.json.gz");res=load(D/"results.json")
    outcomes={z["q"]:z for z in load(D/"outcomes.json.gz")};assert len(outcomes)==len(gold)==len(preds)
    count=collections.Counter();seen_issues=collections.defaultdict(list)
    for p in preds:
        q=p["q"];dates=(p["prev"],p["edit"],p["next"]);assert list(dates)==sorted(set(dates))
        row=outcomes[q];truth=dict(gold[q]["observed"])
        assert len(p["mem"]["H"])==len(p["mem"]["Tstar"])
        ref=set(tuple(v) for v in p["mem"]["F"])
        for m,mem in p["mem"].items():
            pairs=set((n,sig) for n,sig in mem);assert len(pairs)==len(mem)<=128 and ref<=pairs
            observed=set(truth.items());hit=len(observed & pairs);wrong=sum(n in truth and (n,v) not in observed for n,v in pairs)
            assert [len(truth),hit,wrong,len(pairs)]==row["metrics"][m]
            if (p["cohort"],p["window"])==("main","strict"):
                seen_issues[p["issue"],m].append((hit,len(truth),wrong))
        count[(p["cohort"],p["window"])]+=1
    primary=res["groups"]["main_strict"];issues={i for i,m in seen_issues}
    for method,v in primary["methods"].items():
        acc=[];wrong=[]
        for issue in issues:
            hits,total,errors=map(sum,zip(*seen_issues[issue,method]));acc.append(hits/total);wrong.append(errors/total)
        assert math.isclose(statistics.mean(acc),v["coverage"]) and math.isclose(statistics.mean(wrong),v["stale"])
    print("Verified episodes",dict(count),"primary clusters",len(issues),"all forecasts",len(gold))
if __name__=="__main__":run()

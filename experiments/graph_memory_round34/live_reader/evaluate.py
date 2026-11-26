"""Native span scores given only the sealed list of source indices delivered at each query."""
from live import *
def pair(rows,a,b,quantity):
    groups=defaultdict(list);diffs=[];n=0
    for row in rows:
        v=row["arms"][a][quantity]-row["arms"][b][quantity]
        groups[row["t"]].append(v);diffs.append(v)
    sizes=np.array([len(v) for v in groups.values()]);sums=np.array([sum(v) for v in groups.values()])
    rng=np.random.default_rng(17215);samples=[]
    for _ in range(80):
        ix=rng.integers(len(sums),size=(100,len(sums)));samples.extend(100*sums[ix].sum(axis=1)/sizes[ix].sum(axis=1))
    return {"pp":100*np.mean(diffs),"CI95":np.quantile(samples,[.025,.975]).tolist(),"wins":int(sum(x>0 for x in diffs)),"losses":int(sum(x<0 for x in diffs))}
def main():
    cert=read(HERE/"seal.json");assert cert["plan"]==sha(HERE/"plan.json")
    refs=read(ref.OFF/"gold-spans.json.gz");previous={(r["q"],r["cut"]):r for r in read(R22/"outcomes.json.gz")}
    results=[]
    for i in range(8):
        p=HERE/f"forecast-{i}.json.gz";assert sha(p)==cert["forecasts"][p.name]
        base=ref.read(ref.TR/f"forecasts-main-{i}.json.gz");items={r["q"]:[RankedNodeRecord.model_validate(n) for n in r["rr"]] for r in base}
        for r in read(p):
            q,cut=r["q"],r["cut"];gold=tuple(SourceSpan.model_validate(z) for z in refs[q]);rr=items[q];arms={};cache={}
            for name,three in r["selected"].items():
                vals=[]
                for budget,sel in zip(BUDGETS,three):
                    key=tuple(sel)
                    if key not in cache:
                        sub=tuple(rr[j] for j in sel);n=sum(k.token_count for k in sub);assert n<=budget
                        metric=span_metrics_under_token_budget(sub,gold,budget)
                        cache[key]=[float(metric.full_support),float(metric.coverage),int(n)]
                    vals.append(cache[key])
                arms[name]=[vals[2][0],vals[2][1],vals[1][1],vals[0][1],vals[2][2]]
            was=previous[q,cut];old=was["arms"]["exact"];a=was["arms"]["dense"]
            assert r["t"]==was["t"] and r["pilot"]==was["pilot"] and arms["dense"][:2]==[a["fs"],a["coverage"]]
            arms["previous"]=[old["fs"],old["coverage"],None,None,old["tokens"]]
            changes={m:r["selected"]["exact"][2]!=r["selected"][m][2] for m in ("frozen","append","final","metadata")}
            results.append({"q":q,"t":r["t"],"cut":cut,"pilot":r["pilot"],"eligible":was["eligible"],"arms":arms,"changed":changes})
    assert len(results)==len(previous)==8000
    save(HERE/"outcomes.json.gz",results);summary={}
    for cut in (25,50,75,100):
        for condition in ("eligible","all"):
            rows=[r for r in results if r["cut"]==cut and not r["pilot"] and (r["eligible"] or condition=="all")]
            stats={k:[float(np.mean([r["arms"][k][idx] for r in rows])) if rows[0]["arms"][k][idx] is not None else None for idx in range(5)] for k in rows[0]["arms"]}
            contrasts={m:{k:pair(rows,"exact",m,j) for j,k in enumerate(["FS2048","C2048"])} for m in ("previous","metadata","frozen","dense","append","final")}
            summary[f"{cut}.{condition}"]={"n":len(rows),"clusters":len({r["t"] for r in rows}),"means":stats,"vs":contrasts,"different2048":{k:sum(r["changed"][k] for r in rows) for k in rows[0]["changed"]}}
    assert summary["50.eligible"]["n"]==901 and summary["50.all"]["n"]==1845
    save(HERE/"results.json",{"arms_metrics":["FS2048","C2048","C1024","C512","spent2048"],"panels":summary,"seal":sha(HERE/"seal.json")})
if __name__=="__main__":main()

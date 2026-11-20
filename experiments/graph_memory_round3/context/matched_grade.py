"""Check both per-decision costs against the unchanged baseline, then re-score on original hidden edits."""
from context import D,read,save,h,rows
import grade
import inspect,types
from concurrent.futures import ProcessPoolExecutor
A=grade.A
def case(k):
    code=inspect.getsource(grade.case).replace('D/f"pred_{k}.jsonl.gz"','D/f"matched_pred_{k}.jsonl.gz"')
    ns={**grade.__dict__,"BUDGETS":(512,)}
    exec(compile(code,"matched_grade_function","exec"),ns)
    rr,n,c=ns["case"](k)
    base=rows(D/f"pred_{k}.jsonl.gz");out=rows(D/f"matched_pred_{k}.jsonl.gz");checked=0
    for original,now in zip(base,out,strict=True):
        assert original[:2]==now[:2]
        b=original[2]["512"]["r2f"];a=now[2]["512"]
        assert a["r2f"]==b
        for arm,(sel,ind,wire) in a.items():
            assert ind<=b[1] and wire<=b[2];checked+=1
    return rr,n,c,checked
def main():
    assert all(h(D/n)==s for n,s in read("matched_prediction_lock.json")["files"].items())
    with ProcessPoolExecutor(5) as ex:data=list(ex.map(case,range(8)))
    rr=[r for s,*_ in data for r in s]
    import gzip,json
    with gzip.open(D/"matched_scores.jsonl.gz","wt",encoding="utf8",compresslevel=3) as f:
        for r in rr:f.write(json.dumps(r,separators=(",",":"))+"\n")
    stats=grade.metrics(rr); stats["length_strata"]={name:grade.metrics([r for r in rr if lo<=r[3]<=hi]) for name,lo,hi in [("1-12",1,12),("13-24",13,24),("25+",25,10**7)]}
    save("matched_results.json",{"budget":512,"token_checks":sum(x[2] for x in data),"checked_against_r2f":sum(x[3] for x in data),"stats":stats})
    print(stats["arms"],flush=True)
if __name__=="__main__":main()

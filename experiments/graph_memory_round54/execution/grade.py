"""Grade model code in isolated author unittest suites, then compute fully paired, class-clustered contrasts."""
import itertools
import numpy as np
from study import *
from isolate import execute
from generate import key

def extracted(text,target):
    text=text.strip()
    if text.startswith("```") and text.endswith("```"):
        lines=text.splitlines()
        if lines[0].strip().lower() in ("```","```python") and lines[-1].strip()=="```":
            text="\n".join(lines[1:-1])
    try:root=ast.parse(textwrap.dedent(text))
    except (SyntaxError,ValueError):return None,"parse"
    if len(root.body)!=1 or not isinstance(root.body[0],ast.FunctionDef) or root.body[0].name!=target:return None,"shape"
    if not safe(root):return None,"guard"
    return root.body[0].body,"executed"

def signflip(x):
    z=np.array([v for v in x if abs(v)>1e-12]);obs=abs(sum(z));count=len(z)
    if obs<1e-12:return dict(p=1.0,n=count)
    if count<=36:
        halves=[]
        for group in [z[:count//2],z[count//2:]]:
            partial=np.array([0.])
            for v in group:partial=np.r_[partial+v,partial-v]
            halves.append(partial)
        a,b=halves;b=np.sort(b)
        extreme=int(np.searchsorted(b,-obs-a+1e-10,side="right").sum()+len(a)*len(b)-np.searchsorted(b,obs-a-1e-10,side="left").sum())
        return dict(p=extreme/2**count,draws=2**count,nonzero=count,kind="exact")
    rng=np.random.default_rng(540273);extreme=0
    for _ in range(1000):
        signs=rng.integers(0,2,(1000,count),dtype=np.int8)*2-1;extreme+=int((np.abs((signs*z).sum(axis=1))>=obs-1e-10).sum())
    return dict(p=(extreme+1)/1000001,draws=1000000,nonzero=count,kind="monte-carlo")
def main():
    assert get("answer-seal.json")["answers"]==sha(D/"answers.json.gz") and get("answer-seal.json")["inputs"]==sha(D/"input-seal.json")
    c=get("contexts.json.gz");a=get("answers.json.gz");t=get("prompts.json.gz");control=get("calibration.json.gz")
    assert get("input-seal.json")["contexts"]==sha(D/"contexts.json.gz") and set(t)==set(a) and all(key(x)==k for k,x in t.items())
    data=get("observations.json.gz");rows={r["task_id"]:r for r in dataset()}
    jobs={};marks={};den={}
    for q,ctx in c.items():
        case=data[q];r=rows[case["task_id"]];den[q]=control[q+"|reference"]["run"]
        for name,h,n in ctx["refs"].values():
            k=q+"|"+h
            if k in marks:continue
            body,why=extracted(a[h]["code"],case["method"])
            marks[k]=why
            if body:
                jobs[k]=dict(id=k,src=patched(r,case["method"],body),test=r["test"],suite=case["test_class"])
    print("Executing",len(jobs),"distinct implementations",flush=True)
    measured=execute(list(jobs.values()),4)
    put("unittest.json.gz",dict(raw=measured,parse=marks,expected_tests=den))
    records={}
    for q,ctx in c.items():
        rec={}
        for arm,(_id,h,n) in ctx["refs"].items():
            k=q+"|"+h;status=marks[k];v=measured.get(k,{})
            ok=bool(v.get("passed",False)) and v.get("run")==den[q]
            if k not in measured:good=0
            elif v.get("run")!=den[q]:good=0;status="timeout" if v.get("timeout") else "harness"
            else:
                good=max(0,den[q]-v.get("failures",0)-v.get("errors",0)-v.get("skipped",0))
                status="pass" if ok else "runtime_error" if v.get("errors",0) else "assertion_failure"
            rec[arm]=dict(pass1=int(ok),fraction=good/den[q],tests_passed=good,total=den[q],status=status)
        records[q]=rec
    order=sorted(records);classes,ix=np.unique([c[k]["cls"] for k in order],return_inverse=True)
    size=np.bincount(ix);rng=np.random.default_rng(540272);draws=rng.integers(len(size),size=(10000,len(size)))
    summary={}
    for arm in ARMS:
        obs=[records[q][arm] for q in order]
        summary[arm]=dict(passed=sum(x["pass1"] for x in obs),n=len(obs),mean_test_fraction=float(np.mean([x["fraction"] for x in obs])),
            passed_tests=sum(x["tests_passed"] for x in obs),total_tests=sum(den.values()),status=dict(Counter(x["status"] for x in obs)))
    comparisons={}
    for left,right in [(ARMS[0],ARMS[1]),(ARMS[0],ARMS[2]),(ARMS[1],ARMS[2])]:
        fields={}
        for metric in ("pass1","fraction"):
            d=np.array([records[q][left][metric]-records[q][right][metric] for q in order])
            total=np.bincount(ix,weights=d);boots=100*total[draws].sum(axis=1)/size[draws].sum(axis=1)
            fields[metric]=dict(delta_pp=100*d.mean(),ci95_pp=list(np.quantile(boots,[.025,.975])),
                 wins=int((d>1e-12).sum()),losses=int((d< -1e-12).sum()),signflip=signflip(total))
        comparisons[left+" vs "+right]=fields
    result=dict(n=len(order),classes=len(classes),different=sum(ctx["refs"][ARMS[0]][1]!=ctx["refs"][ARMS[1]][1] for ctx in c.values()),
        different_addresses=sum(ctx["refs"][ARMS[0]][0]!=ctx["refs"][ARMS[1]][0] for ctx in c.values()),
        mean_evidence=np.mean([ctx["width"] for ctx in c.values()]),unique_generated=len(a),tested=len(jobs),
        summaries=summary,contrasts=comparisons)
    put("records.json.gz",records);put("results.json",result)
    put("grade-seal.json",dict(results=sha(D/"results.json"),records=sha(D/"records.json.gz"),unittest=sha(D/"unittest.json.gz"),
        answer=sha(D/"answer-seal.json"),source=SOURCE_HASH,code=sha(Path(__file__)),runner=sha(D/"isolate.py")))
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()

"""Seal all requests first; grade real completions against the unmodified official method-specific suites."""
import ast,collections,concurrent.futures,gzip,json,math,re,textwrap
import numpy as np
from common import D,read,save,sha
from prepare import execute,grade_input,taskid
def pair(v,w,groups):
    d=np.asarray(v)-w
    cats=sorted(set(groups));m=np.array([[sum(d[j] for j,c in enumerate(groups) if c==s),sum(c==s for c in groups)] for s in cats]);rng=np.random.default_rng(181126);bs=rng.integers(len(cats),size=(10000,len(cats)));bb=m[bs].sum(axis=1)
    n=int((d!=0).sum());wins=int((d>0).sum());losses=int((d<0).sum())
    s=min(wins,losses)
    return dict(delta=float(d.mean()),ci=np.quantile(bb[:,0]/bb[:,1],[.025,.975]).tolist(),wins=wins,losses=losses,macro=float(np.mean(m[:,0]/m[:,1])),p_exact_discordant=min(1.,2*sum(math.comb(n,j) for j in range(s+1))/2**n) if n else 1.)
def response(rec):
    return rec["reply"]["choices"][0]["message"].get("content") or ""
def attrs(src):
    try:f=ast.parse(textwrap.dedent(src))
    except (SyntaxError,IndentationError):return set()
    return {n.attr for n in ast.walk(f) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=="self"}
def main():
    controls=read(D/"calibration.json");packets={r["id"]:r for r in read(D/"packets.json")};arms=list(next(iter(packets.values()))["mem"])
    visible={r["id"]:r for r in read(D/"visible.json")};assign=read(D/"assignment.json")
    for n,h in read(D/"method_lock.json").items():assert sha((D/n).read_bytes())==h
    for n,h in read(D/"decision_lock.json").items():assert sha((D/"calls"/n).read_bytes())==h
    src={taskid(c,m):(c,m) for c in read(D/"ClassEval_data.json") for m in c["methods_info"]}
    work={};receipts={}
    for it in assign:
        i=it["id"];c,m=src[i];blob=grade_input(c,m)
        for a,key in it["arms"].items():
            if key not in work:
                rec=read(D/"calls"/(key+".json.gz"));raw=response(rec)
                assert sha(json.dumps(rec["request"],sort_keys=True,ensure_ascii=True))==key
                assert rec["request"]["messages"][1]["content"].endswith(visible[i]["desc"])
                work[key]={**blob,"grade":"generated","candidate":raw}
    ordered=list(work)
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        for key,s in zip(ordered,pool.map(execute,[work[k] for k in ordered])):receipts[key]=s
    save(D/"grading.json.gz",receipts);items=[]
    for r in assign:
        i=r["id"];c,m=src[i];clsnode=next(x for x in ast.parse(c["solution_code"]).body if isinstance(x,ast.ClassDef) and x.name==c["class_name"])
        target=next(x for x in clsnode.body if isinstance(x,ast.FunctionDef) and x.name==m["method_name"])
        goldattrs=attrs(ast.unparse(target));base=controls[i][1];total=base["total"];assert total>0
        prevattrs=set().union(*(attrs(p["src"]) for p in visible[i]["previous"]))
        available=goldattrs&prevattrs
        metrics={}
        for a,key in r["arms"].items():
            s=receipts[key];rec=read(D/"calls"/(key+".json.gz"));mem=packets[i]["mem"][a];found=set(re.findall(r"\bself\.(\w+)",mem));generated=attrs(response(rec));usage=rec["reply"]["usage"]
            if s.get("total"):assert s["total"]==total
            metrics[a]=dict(pass_all=int(s["status"]=="pass"),passed=int(s.get("passed",0)),total=total,
                parsed=int(s["status"] not in ("invalid","process","harness")),memory_tokens=packets[i]["tokens"][a],prompt_tokens=usage["prompt_tokens"],output_tokens=usage["completion_tokens"],seconds=rec["elapsed"],
                gold_mention=sum(x in found for x in available),shared=len(available),choice_key=key,finish=rec["reply"]["choices"][0]["finish_reason"])
        items.append(dict(id=i,cls=c["class_name"],metrics=metrics))
    save(D/"per_item.json",items)
    def summary(sub):
        groups=[x["cls"] for x in sub];answers={};contrasts={}
        val=lambda a,k:np.array([x["metrics"][a][k] for x in sub])
        for a in arms:
            answer={}
            for k in ("pass_all","passed","total","parsed","memory_tokens","prompt_tokens","output_tokens","gold_mention","shared"):answer[k]=int(val(a,k).sum())
            answer["seconds"]=float(val(a,"seconds").sum())
            answers[a]=answer
            contrasts[a]={"pass_all":pair(val("graph","pass_all"),val(a,"pass_all"),groups),"method_test_fraction":pair(val("graph","passed")/val("graph","total"),val(a,"passed")/val(a,"total"),groups)}
        return {"n":len(sub),"classes":len(set(groups)),"scores":answers,"graph_minus":contrasts}
    active=[i for i in items if i["metrics"]["graph"]["choice_key"]!=i["metrics"]["bm25_line"]["choice_key"]]
    summ={"main":summary(items),"distinct_primary_prompts":summary(active) if active else None,"unique_calls":len(work),"status":dict(collections.Counter(x["status"] for x in receipts.values())),"native_usage":{k:sum(read(D/"calls"/(key+".json.gz"))["reply"]["usage"][k] for key in work) for k in ("prompt_tokens","completion_tokens")}}
    save(D/"results.json",summ)
if __name__=="__main__":main()

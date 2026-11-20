"""Post-compaction address selection using only prefix tests and bounded single-statement interventions."""
import ast, collections, concurrent.futures, copy, difflib, io, itertools, json, math, os, random, re, shutil, sys, time, tokenize, types
from pathlib import Path
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
import run as r
METHODS=["balanced","random"]
def task(n):return D/"tasks"/n
def setup():
    assert not (D/"lock.json").exists()
    ids=r.eligible();files=[D/"experiment.py",D/"PROTOCOL_RU.md",r.D/"input_lock.json",r.D/"run.py",r.D/"worker.py"]
    for n in ids:
        t=r.ts(n);s=r.fn(r.Q/"python_programs",n).read_text("utf8");out=task(n);out.mkdir(parents=True,exist_ok=True)
        early=r.get(t/"prefix.json.gz");mod=ast.parse(r.fn(r.Q/"python_testcases","test_"+n).read_text("utf8"))
        mod.body=[f for f in mod.body if not isinstance(f,ast.FunctionDef) or not f.name.startswith("test") or f.name in early]
        cases=ast.unparse(mod);assert set(r.names(cases))==set(early)
        for file,content in [("source.py.txt",s),("early_tests.py.txt",cases)]:
            p=out/file;p.write_text(content,encoding="utf8");files.append(p)
        p=out/"visible.json.gz";r.dump(p,early);files.append(p)
    r.dump(D/"lock.json",{"ids":ids,"files":{str(p):r.hf(p) for p in files}})
def locked():
    amend=r.get(D/"amendment_lock.json");assert r.hf(D/"version2.py")==amend["script_sha256"] and r.hf(D/"AMENDMENT_RU.md")==amend["note_sha256"];lock=r.get(D/"lock.json");assert all(r.hf(Path(p))==h for p,h in lock["files"].items());return lock["ids"]
def mutators(n,s,visible):
    tree=ast.parse(s);lines=s.splitlines(keepends=True);starts=[0]
    for k in lines:starts.append(starts[-1]+len(k))
    allowed={v for x in visible.values() if x["status"]=="failed" for v in x["lines"]}
    variables=sorted({x.arg for x in ast.walk(tree) if isinstance(x,ast.arg)}|{x.id for x in ast.walk(tree) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Store)})
    attrs=sorted({x.attr for x in ast.walk(tree) if isinstance(x,ast.Attribute)})
    cand={}
    def add(i,j,replacement,lineno,kind):
        if lineno not in allowed:return
        mutation=s[:i]+replacement+s[j:]
        if s==mutation:return
        try:ast.parse(mutation)
        except (SyntaxError,ValueError):return
        sig=r.key(mutation)
        if sig not in cand:cand[sig]={"id":sig,"site":lineno,"kind":kind,"begin":i,"end":j,"replacement":replacement}
    for x in ast.walk(tree):
        if isinstance(x,ast.Name) and x.id in variables and x.lineno in allowed:
            for alt in variables:add(starts[x.lineno-1]+x.col_offset,starts[x.end_lineno-1]+x.end_col_offset,alt,x.lineno,1)
        if isinstance(x,ast.Attribute) and x.lineno in allowed:
            end=starts[x.end_lineno-1]+x.end_col_offset
            for alt in attrs:add(end-len(x.attr),end,alt,x.lineno,0)
        if isinstance(x,ast.stmt) and not isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and getattr(x,"lineno",0) in allowed:
            i=starts[x.lineno-1]
            for a in variables:
                for b in variables:
                    if a!=b:add(i,i," "*x.col_offset+a+" = "+b+"\n",x.lineno,3)
    ops={"+":"-","-":"+","*":"//","//":"*","<":">=","<=":">",">":"<=",">=":"<","==":"!=","!=":"=="}
    for tok in tokenize.generate_tokens(io.StringIO(s).readline):
        k=tok.start[0]
        if k not in allowed:continue
        repl=[ops[tok.string]] if tok.string in ops else ["0","1","2"] if tok.type==tokenize.NUMBER and tok.string in ["0","1","2"] else []
        for alt in repl:add(starts[k-1]+tok.start[1],starts[k-1]+tok.end[1],alt,k,2)
    return list(cand.values())
def fast(n,s,case_text,targets):
    import pytest
    pytest.use_correct=False
    for folder in [r.Q,r.Q/"python_testcases"]:
        if str(folder) not in sys.path:sys.path.insert(0,str(folder))
    states={}
    for k in targets:
        prog=types.ModuleType("python_programs."+n)
        filename="<probe-target:"+n+">"
        sys.modules["python_programs."+n]=prog
        ns={"__name__":"visible_tests"}
        count=0
        def trace(frame,event,arg):
            nonlocal count
            if frame.f_code.co_filename not in (filename,"<visible_tests>"):return None
            if event=="line":
                count+=1
                if count>15000:raise TimeoutError("line budget")
            return trace
        try:
            exec(compile(s,filename,"exec"),prog.__dict__)
            exec(compile(case_text,"<visible_tests>","exec"),ns)
            sys.settrace(trace)
            ns[k]()
            passed=True
        except (Exception,RecursionError):passed=False
        finally:sys.settrace(None)
        states[k]="passed" if passed else "failed"
    return states
def probe(n):
    import pytest
    start=time.monotonic();p=task(n);s=(p/"source.py.txt").read_text("utf8");cases=(p/"early_tests.py.txt").read_text("utf8")
    vis=r.get(p/"visible.json.gz");targets=sorted(vis); states={k:v["status"] for k,v in vis.items()}
    actual=fast(n,s,cases,targets);agree=(actual==states)
    assert agree,(n,states,actual)
    pool=mutators(n,s,vis) if "failed" in states.values() else []
    groups=collections.defaultdict(list)
    for x in pool:groups[x["site"]].append(x)
    for site,items in groups.items():items.sort(key=lambda a:(a["kind"],r.key("r9-probe-choice|"+n+"|"+a["id"])))
    scores=[v[2][0] for v in r.rank(vis,"lines")];sites=[k for k in scores if k in groups]
    balanced=[groups[site][j] for j in range(max((len(v) for v in groups.values()),default=0)) for site in sites if j<len(groups[site])][:32]
    rand=sorted(pool,key=lambda a:r.key("r9-probe-random|"+n+"|"+a["id"]))[:len(balanced)]
    chosen={"balanced":balanced,"random":rand}
    tested={};assigned={};stats={}
    for m,ls in chosen.items():
        for a in ls:
            if a["id"] in tested:continue
            mutated=s[:a["begin"]]+a["replacement"]+s[a["end"]:]
            assert r.key(mutated)==a["id"]
            t=time.monotonic();rs=fast(n,mutated,cases,targets)
            tested[a["id"]]={**a,"outcomes":rs,"seconds":time.monotonic()-t}
        scores=[]
        for a in ls:
            obs=tested[a["id"]]["outcomes"]
            up=sum(states[k]=="failed" and obs[k]=="passed" for k in targets)
            down=sum(states[k]=="passed" and obs[k]=="failed" for k in targets)
            if up and not down:scores.append((up,a["site"]))
        best=max((x[0] for x in scores),default=0)
        hits=collections.Counter(site for u,site in scores if u==best)
        assigned[m]=min(hits,key=lambda site:(-hits[site],site)) if hits else None
        stats[m]={"probes":len(ls),"test_calls":len(ls)*len(targets),"max_recovered":best,"probe_seconds":sum(tested[a["id"]]["seconds"] for a in ls)}
    r.dump(p/"probes.json.gz",{"prefix_controls":actual,"pool_size":len(pool),"chosen":{k:[x["id"] for x in v] for k,v in chosen.items()},"physical":tested,"assigned":assigned,"cost":stats,"physical_seconds":time.monotonic()-start})
    print(n,assigned,flush=True)
def schedule():
    ids=locked()
    with concurrent.futures.ProcessPoolExecutor(3) as ex:list(ex.map(probe,ids))
    paths=[]
    for n in ids:
        p=task(n);log=r.get(p/"probes.json.gz");paths.append(p/"probes.json.gz")
        base=r.get(r.ts(n)/"messages.json.gz")["off"]
        messages={m:base.replace("Retained source address: ---.","Retained source address: "+(f"{a:03d}" if a else "---")+".") for m,a in log["assigned"].items()}
        assert all(re.sub(r"Retained source address: (---|\d+)\.","",x)==re.sub(r"Retained source address: (---|\d+)\.","",base) for x in messages.values())
        out=p/"messages.json.gz";r.dump(out,messages);paths.append(out)
    r.dump(D/"input_lock.json",{"files":{str(p):r.hf(p) for p in paths},"lock":r.hf(D/"lock.json")})
def checked():
    ids=locked();lock=r.get(D/"input_lock.json")
    assert lock["lock"]==r.hf(D/"lock.json") and all(r.hf(Path(p))==s for p,s in lock["files"].items())
    return ids
def infer():
    ids=checked();lib=r.lib();lib.D=D
    for n in ids:
        src=r.get(r.ts(n)/"messages.json.gz");orig=r.get(r.D/"assign.json")[n];tp=r.get(task(n)/"messages.json.gz")
        for m,message in tp.items():
            for om,existing in src.items():
                if existing==message:
                    k=orig[om];dest=D/"calls"/(k+".json.gz");dest.parent.mkdir(exist_ok=True);shutil.copyfile(r.D/"calls"/dest.name,dest)
                    break
    prev=sorted(f.name.split(".")[0] for f in (D/"calls").glob("*.json.gz"));ass={}
    for n in ids:
        tp=r.get(task(n)/"messages.json.gz");ass[n]={}
        for m in sorted(METHODS,key=lambda a:r.key("probe-order|"+n+"|"+a)):
            k,_=lib.call(n,"repair",r.SYS,tp[m],600);ass[n][m]=k
    r.dump(D/"assign.json",ass)
    fs=[D/"assign.json",*(D/"calls").glob("*.json.gz")]
    r.dump(D/"answer_lock.json",{"prior_response_keys":prev,"input":r.hf(D/"input_lock.json"),"files":{str(p):r.hf(p) for p in fs}})
def outputs():
    ids=checked();lock=r.get(D/"answer_lock.json");assert lock["input"]==r.hf(D/"input_lock.json") and all(r.hf(Path(p))==v for p,v in lock["files"].items());return ids
def grade(n):
    base=(task(n)/"source.py.txt").read_text("utf8");results={}
    original=r.get(r.D/"assign.json")[n];old=r.get(r.ts(n)/"grades.json");ass=r.get(D/"assign.json")[n]
    repeat={}
    for m in METHODS:
        k=ass[m];reply=r.get(D/"calls"/(k+".json.gz"))["response"]["choices"][0]["message"]["content"]
        reason=""
        try:new=r.patched(base,reply)
        except (ValueError,TypeError,KeyError,SyntaxError,AttributeError) as ex:reason=str(ex)[:160];new=base
        digest=r.key(new)
        previous=next((a for a,v in old.items() if v["source_sha"]==digest),None)
        if previous:out=old[previous]["tests"];reuse="r9/"+previous
        elif new==base:out=r.get(r.ts(n)/"base/testdata/outcomes.json");reuse="base"
        elif digest in repeat:out,reuse=repeat[digest]
        else:
            orig_ts=r.ts;r.ts=task
            try:out,_=r.test(n,m,new)
            finally:r.ts=orig_ts
            reuse=None;repeat[digest]=(out,m)
        results[m]={"applied":new!=base,"reason":reason,"source_sha":digest,"tests":out,"reused_test":reuse}
    r.dump(task(n)/"grades.json",results)
def grade_all():
    ids=outputs()
    with concurrent.futures.ProcessPoolExecutor(3) as ex:list(ex.map(grade,ids))
def modelcost(keys):
    ret=collections.Counter()
    for k in keys:
        x=r.get(D/"calls"/(k+".json.gz"));u=x["response"]["usage"];ret.update(calls=1,prompt=u["prompt_tokens"],output=u["completion_tokens"],seconds=sum(a["elapsed"] for a in x["attempts"]))
    return ret
def report():
    ids=outputs();main={a["id"]:a for a in r.get(r.D/"rows.json")};ass=r.get(D/"assign.json");rows=[];aggregate={m:collections.Counter() for m in METHODS}
    physical=collections.Counter()
    for n in ids:
        log=r.get(task(n)/"probes.json.gz");pre=r.get(r.ts(n)/"preflight.json");g=r.get(task(n)/"grades.json");physical.update(probes=len(log["physical"]),test_calls=len(log["physical"])*len(pre["early"]),elapsed_s=log["physical_seconds"])
        row={"id":n,"base":main[n]["arms"]["off"],"line":main[n]["arms"]["line"],"oracle":main[n]["arms"]["oracle"]}
        for m in METHODS:
            t=g[m]["tests"];rs=t["states"];a=log["assigned"][m]
            v={"anchor":a,"address_correct":a in pre["gold_lines"],"all_pass":bool(t["complete"] and g[m]["applied"] and all(z=="passed" for z in rs.values())),
               "hold_pass":all(rs.get(k)=="passed" for k in pre["hold"]),"passed":sum(z=="passed" for z in rs.values()),"total":len(rs),"source_sha":g[m]["source_sha"],"applied":g[m]["applied"],"complete":t["complete"],**log["cost"][m]}
            row[m]=v
            aggregate[m].update({k:v[k] for k in ["address_correct","all_pass","hold_pass","passed","total","applied","complete","probes","test_calls","probe_seconds"]})
        rows.append(row)
    results={"tasks":len(ids),"physical_probes":physical,"methods":{},"comparisons":{}}
    for m in METHODS:results["methods"][m]={**aggregate[m],"model_cost":modelcost([ass[n][m] for n in ids])}
    for b,m in [("base","balanced"),("line","balanced"),("random","balanced"),("base","random")]:
        d=[int(z[m]["all_pass"])-int(z[b]["all_pass"]) for z in rows];w,l=d.count(1),d.count(-1);k=w+l
        results["comparisons"][b+"->"+m]={"wins":w,"losses":l,"ties":len(ids)-k,"p":min(1,2*sum(math.comb(k,j) for j in range(min(w,l)+1))/2**k) if k else 1}
    prior=set(r.get(D/"answer_lock.json")["prior_response_keys"]);allkeys={k for v in ass.values() for k in v.values()};results["prior_model_calls"]=modelcost(sorted(prior));results["new_model_calls"]=modelcost(sorted(allkeys-prior))
    r.dump(D/"results.json",results);r.dump(D/"rows.json",rows)
def verify():
    ids=outputs();before=[r.hf(D/k) for k in ["results.json","rows.json"]];report();assert before==[r.hf(D/k) for k in ["results.json","rows.json"]]
    for n in ids:
        p=task(n);log=r.get(p/"probes.json.gz");pr=r.get(r.ts(n)/"preflight.json")
        assert set(r.names((p/"early_tests.py.txt").read_text("utf8")))==set(pr["early"]) and not set(pr["hold"])&set(log["prefix_controls"])
        assert len(log["chosen"]["random"])==len(log["chosen"]["balanced"])<=32
        for a in log["physical"].values():assert set(a["outcomes"])==set(pr["early"])
    r.dump(D/"verification.json",{"tasks":len(ids),"result_sha":before[0],"rows_sha":before[1],"equal_probe_budgets":True,"late_tests_absent_in_probe_runner":True})
if __name__=="__main__":{"setup":setup,"schedule":schedule,"infer":infer,"grade":grade_all,"report":report,"verify":verify}[sys.argv[1]]()

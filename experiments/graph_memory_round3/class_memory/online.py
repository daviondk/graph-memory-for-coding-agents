"""Teacher-free class generation; writer receives only methods generated earlier in the same policy arm."""
import ast,collections,concurrent.futures,json,sys,time,urllib.request
from common import D,read,save,sha
from prepare import SAFE,taskid,execute,method_body,interface
from policy import memories,prompt
from solve import SYSTEM,BASE
from worker import parse_candidate
def cls_ast(r):
    return next(n for n in ast.parse(r["skeleton"]).body if isinstance(n,ast.ClassDef) and n.name==r["class_name"])
def ref_methods(r):
    cls=next(n for n in ast.parse(r["solution_code"]).body if isinstance(n,ast.ClassDef) and n.name==r["class_name"])
    return {f.name:ast.unparse(f) for f in cls.body if isinstance(f,ast.FunctionDef)}
def safe_skeleton(r):
    cls=cls_ast(r);allowed={m["method_name"] for m in r["methods_info"]}
    decl={f.name for f in cls.body if isinstance(f,ast.FunctionDef)}
    if decl-allowed-{"__init__"} or allowed-decl:return False
    for f in cls.body:
        if isinstance(f,ast.FunctionDef) and f.name in allowed:
            if any(not (isinstance(s,ast.Pass) or isinstance(s,ast.Expr) and isinstance(s.value,ast.Constant) or isinstance(s,ast.Raise)) for s in f.body):return False
    return True
def assembled(r,methods):
    c=cls_ast(r)
    for j,x in enumerate(c.body):
        if not isinstance(x,ast.FunctionDef) or x.name not in methods:continue
        f=ast.parse(methods[x.name]).body[0];f.decorator_list=x.decorator_list;c.body[j]=f
    return ast.unparse(c)
def suites(r):
    meta={v["test_class"]:v["method_name"] for v in r["methods_info"]};raw=ast.parse(r["test"])
    extracted={n.name:ast.unparse(n) for n in raw.body if isinstance(n,ast.ClassDef)}
    return [(n,meta.get(n,"INTEGRATION"),extracted[n]) for n in r["test_classes"]]
def grade(r,methods):
    code=assembled(r,methods);first=r["methods_info"][0]["method_name"];results={}
    for n,role,suite in suites(r):
        receipt=execute(dict(grade="reference",source=code,name=first,imports=r["import_statement"],tests=suite,testclass=n,**{"class":r["class_name"]}))
        results[n]=dict(role=role,receipt=receipt)
    return results
def prepare():
    rows=[r for r in read(D/"ClassEval_data.json") if r["class_name"] in SAFE and 3<=len(r["methods_info"])<=5]
    candidates=[];log={}
    for r in sorted(rows,key=lambda r:sha("r3online|"+r["class_name"])):
        try:
            if not safe_skeleton(r):log[r["task_id"]]="invalid or incomplete public skeleton";continue
            ref=ref_methods(r);ref={m["method_name"]:ref[m["method_name"]] for m in r["methods_info"]}
            checked=grade(r,ref);log[r["task_id"]]=checked
            if not all(v["receipt"]["status"]=="pass" and not v["receipt"]["skipped"] for v in checked.values()):continue
            if not any(v["role"]=="INTEGRATION" for v in checked.values()):continue
            candidates.append(r)
            if len(candidates)==14:break
        except (ValueError,KeyError,TypeError,SyntaxError) as exc:log[r["task_id"]]="source "+type(exc).__name__
    save(D/"online_reference.json",log)
    public=[dict(id=r["task_id"],cls=r["class_name"],summary=r["class_description"],imports=r["import_statement"],constructor=r["class_constructor"],interfaces=[interface(m) for m in r["methods_info"]],targets=[(m["method_name"],m["method_description"]) for m in r["methods_info"]]) for r in candidates]
    save(D/"online_visible.json",public);print("online selected",len(candidates),sum(len(c["targets"]) for c in public),flush=True)
def call(req):
    raw=json.dumps(req,sort_keys=True,ensure_ascii=True);key=sha(raw);path=D/"online_calls"/(key+".json.gz")
    if not path.exists():
        if (D/"calls"/path.name).exists():
            save(path,read(D/"calls"/path.name))
        else:
            t=time.monotonic()
            for trial in range(3):
                try:
                    q=urllib.request.Request(BASE+"/v1/chat/completions",data=raw.encode(),headers={"Content-Type":"application/json"})
                    with urllib.request.urlopen(q,timeout=130) as f:rep=json.load(f)
                    break
                except (TimeoutError,OSError):
                    if trial==2:raise
                    time.sleep(2)
            save(path,dict(key=key,request=req,reply=rep,elapsed=time.monotonic()-t))
    rec=read(path);return key,(rec["reply"]["choices"][0]["message"].get("content") or "")
def solve():
    public=read(D/"online_visible.json");names=["graph","bm25_line","full"];output=[]
    for c in public:
        histories={a:[] for a in names};logs={a:[] for a in names}
        for name,desc in c["targets"]:
            for a in sorted(names,key=lambda x:sha(c["id"]+name+x)):
                i=c["id"]+"/"+name;row={**c,"id":i,"name":name,"desc":desc,"previous":histories[a]}
                mem=memories(row)[a] if histories[a] else ""
                req=dict(model="qwen38-27b-ud-q4km",messages=[dict(role="system",content=SYSTEM),dict(role="user",content=prompt(row,mem))],max_tokens=384,seed=int(sha("decode|"+i)[:7],16),temperature=0,repeat_penalty=1,stream=False,chat_template_kwargs={"enable_thinking":False},cache_prompt=False)
                key,raw=call(req)
                try:src=ast.unparse(parse_candidate(raw,name));valid=True
                except (SyntaxError,ValueError,TypeError,IndentationError):
                    src=f"def {name}(self, *args, **kwargs):\n    raise NotImplementedError";valid=False
                histories[a].append(dict(method=name,src=src));logs[a].append(dict(name=name,key=key,valid=valid,memory=mem))
        output.append(dict(id=c["id"],cls=c["cls"],histories=histories,logs=logs));save(D/"online_partial.json.gz",output);print("online classes",len(output),flush=True)
    save(D/"online_programs.json.gz",output)
    save(D/"online_decision_lock.json",{str(p.relative_to(D)):sha(p.read_bytes()) for p in [D/"online_programs.json.gz",D/"online_method_lock.json",*sorted((D/"online_calls").glob("*.gz"))]})
def evaluate():
    from grade import pair
    for n,h in read(D/"online_decision_lock.json").items():assert sha((D/n).read_bytes())==h
    raw={r["task_id"]:r for r in read(D/"ClassEval_data.json")};output=read(D/"online_programs.json.gz");items=[];metric={};arms=("graph","bm25_line","full")
    for c in output:
        r=raw[c["id"]];values={};ref=read(D/"online_reference.json")[c["id"]]
        for a in arms:
            methods={h["method"]:h["src"] for h in c["histories"][a]};s=grade(r,methods);exp=sum(v["receipt"]["total"] for v in ref.values())
            passes=[v["receipt"]["status"]=="pass" for v in s.values()];meth=[v["receipt"]["status"]=="pass" for v in s.values() if v["role"]!="INTEGRATION"]
            integ=[v["receipt"]["status"]=="pass" for v in s.values() if v["role"]=="INTEGRATION"];usage=[read(D/"online_calls"/(l["key"]+".json.gz"))["reply"]["usage"] for l in c["logs"][a]]
            values[a]=dict(pass_all=int(all(passes)),method=sum(meth),methods=len(meth),integration=int(all(integ)),tests=sum(v["receipt"].get("passed",0) for v in s.values()),total=exp,
                           prompt=sum(x["prompt_tokens"] for x in usage),completion=sum(x["completion_tokens"] for x in usage),suites=s)
        items.append(dict(id=c["id"],cls=c["cls"],values=values))
    save(D/"online_scored.json.gz",items);groups=[q["cls"] for q in items];res={}
    import numpy as np
    for a in arms:
        res[a]={k:sum(r["values"][a][k] for r in items) for k in ["pass_all","method","methods","integration","tests","total","prompt","completion"]}
        v=lambda arm:np.array([x["values"][arm]["pass_all"] for x in items])
        res[a]["graph_minus_all"]=pair(v("graph"),v(a),groups)
    save(D/"online_results.json",{"classes":len(items),"distinct_requests":len(list((D/"online_calls").glob("*.gz"))),"scores":res})
if __name__=="__main__":
    prepare()
    deps=[D/f for f in ["ONLINE_PROTOCOL.md","online.py","worker.py","policy.py","prepare.py","solve.py","online_visible.json","online_reference.json"]]
    save(D/"online_method_lock.json",{p.name:sha(p.read_bytes()) for p in deps});solve();evaluate()

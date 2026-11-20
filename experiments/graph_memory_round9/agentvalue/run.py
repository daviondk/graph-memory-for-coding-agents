"""Paired post-compaction program correction with one stored address, CPU controls and native tests."""
import ast, collections, concurrent.futures, difflib, gzip, hashlib, importlib.util, io, json, math, os, re, shutil, subprocess, sys, time, tokenize
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parents[1]
Q=Path("D:/CodexResearch/x20-session3-quixbugs")
LEG=W/"memory_session3/repair"
R8=W/"graph_memory_round8/agent"
ENV=W/"graph_memory_round6/repair/env/Scripts/python.exe"
NAMES=["off","line","edge","oracle"]
def get(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def dump(p,x):
    p.parent.mkdir(exist_ok=True,parents=True)
    b=(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=None if p.suffix==".gz" else 2)+"\n").encode()
    if p.suffix==".gz":b=gzip.compress(b,mtime=0)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(b);tmp.replace(p)
def sha(b):return hashlib.sha256(b).hexdigest()
def hf(p):return sha(p.read_bytes())
def key(s):return sha(s.encode())
def ts(name):return D/"tasks"/name
def fn(t,n):return t/(n+".py")
def names(src):
    return [n.name for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name.startswith("test")]
def freeze():
    assert not (D/"protocol_lock.json").exists()
    assert subprocess.check_output(["git","-C",str(Q),"rev-parse","HEAD"],text=True).strip()=="4257f44b0ff1181dedaedee6a447e133219fcebf"
    cohort=sorted(p.stem[5:] for p in (Q/"python_testcases").glob("test_*.py") if not fn(Q/"json_testcases",p.stem[5:]).with_suffix(".json").exists())
    old={r["name"] for r in get(LEG/"roster.json") if r["eligible"]}
    assert len(cohort)==9 and not old.intersection(cohort)
    source_hash={}
    for n in cohort:
        for p in (fn(Q/"python_programs",n),fn(Q/"correct_python_programs",n),fn(Q/"python_testcases","test_"+n)):
            source_hash[str(p)]=hf(p)
    for p in (Q/"conftest.py",Q/"python_testcases/node.py",Q/"python_programs/node.py",LEG/"roster.json",R8/"harness.py",D/"worker.py",D/"run.py",D/"PROTOCOL_RU.md",D/"start_server.ps1",W/"graph_memory_round6/repair/model_receipt.json",W/"graph_memory_round6/repair/runtime_receipt.json"):
        source_hash[str(p)]=hf(p)
    dump(D/"protocol_lock.json",{"cohort":cohort,"prior_quixbugs_tasks":sorted(old),"files":source_hash,"python":subprocess.check_output([str(ENV),"-c","import sys,pytest;print(sys.version,pytest.__version__)"],text=True).strip()})
def locked():
    r=get(D/"protocol_lock.json");assert all(hf(Path(p))==s for p,s in r["files"].items())
    return r["cohort"]
def copyroot(n,side,source):
    root=ts(n)/side/"checkout"
    for target,src in [("conftest.py",Q/"conftest.py"),("python_testcases/node.py",Q/"python_testcases/node.py"),("python_programs/node.py",Q/"python_programs/node.py"),("python_testcases/test_"+n+".py",fn(Q/"python_testcases","test_"+n))]:
        p=root/target;p.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(src,p)
    fn(root/"python_programs",n).write_text(source,encoding="utf8")
    return root
def test(n,side,source):
    root=copyroot(n,side,source);out=ts(n)/side/"testdata";out.mkdir(exist_ok=True)
    start=time.monotonic()
    try:
        proc=subprocess.run([str(ENV),str(D/"worker.py"),str(root),n,str(out)],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                 timeout=25,env={**os.environ,"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"})
        (out/"pytest.log").write_bytes(proc.stdout)
        r=get(out/"trace.json.gz")
    except subprocess.TimeoutExpired as ex:
        (out/"pytest.log").write_bytes(ex.stdout or b"");r={"rc":None,"records":{},"xml":{}}
    wanted=names(fn(Q/"python_testcases","test_"+n).read_text("utf8"));actual={k:x.get("status") for k,x in r["records"].items()}
    clean=(r["rc"] in (0,1) and set(actual)==set(wanted) and actual==r["xml"] and all(v in ["passed","failed"] for v in actual.values()))
    ret={"complete":clean,"states":actual,"test_seconds":time.monotonic()-start}
    dump(out/"outcomes.json",ret);return ret,r["records"]
def tokens_code(s):
    tree=ast.parse(s);selected=set()
    for f in tree.body:
        if not isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
        selected.update(range(f.lineno,f.end_lineno+1))
        for v in ast.walk(f):
            if isinstance(v,ast.Expr) and isinstance(v.value,ast.Constant) and isinstance(v.value.value,str):
                selected.difference_update(range(v.lineno,v.end_lineno+1))
    by=collections.defaultdict(list)
    ignore={tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE,tokenize.INDENT,tokenize.DEDENT,tokenize.ENDMARKER}
    for t in tokenize.generate_tokens(io.StringIO(s).readline):
        if t.start[0] in selected and t.type not in ignore:by[t.start[0]].append(t.string)
    return sorted((n,tuple(v)) for n,v in by.items())
def oracle(before,after):
    a,b=tokens_code(before),tokens_code(after);ret=set()
    for op,i,j,k,l in difflib.SequenceMatcher(None,[x[1] for x in a],[x[1] for x in b],autojunk=False).get_opcodes():
        if op!="equal": ret.update(x[0] for x in a[i:j] or [a[min(i,len(a)-1)]])
    return sorted(ret)
def rank(prefix,kind):
    fail=sum(x["status"]=="failed" for x in prefix.values())
    where=collections.defaultdict(lambda:[0,0,0])
    for r in prefix.values():
        vals=[tuple(v) if isinstance(v,list) else (v,) for v in r[kind]]
        for v in set(vals):
            where[v][0 if r["status"]=="failed" else 1]+=1
        if r["status"]=="failed":
            for v in set(vals[-3:]):where[v][2]+=1
    ranked=[]
    for v,(f,p,late) in where.items():
        if f:ranked.append((f/math.sqrt(fail*(f+p)),late,v,f,p))
    ranked.sort(key=lambda a:(-a[0],-a[1],a[2]))
    return ranked
def prepare(n):
    bad=fn(Q/"python_programs",n).read_text("utf8");gold=fn(Q/"correct_python_programs",n).read_text("utf8")
    base,trace=test(n,"base",bad);ref,_=test(n,"gold",gold)
    approved=base["complete"] and ref["complete"] and "failed" in base["states"].values() and set(ref["states"].values())=={"passed"}
    ids=sorted(names(fn(Q/"python_testcases","test_"+n).read_text("utf8")),key=lambda t:key("r9-split|"+n+"|"+t));visible=ids[:(len(ids)+1)//2];hold=ids[len(visible):]
    p={k:trace[k] for k in visible if k in trace}
    oracles=oracle(bad,gold);assert oracles
    a=rank(p,"lines");b=rank(p,"edges")
    line=a[0][2][0] if a else None;edge=b[0][2][0] if b else None
    item={"name":n,"valid":approved,"early":visible,"hold":hold,"failed_early":sum(x["status"]=="failed" for x in p.values()),"anchor":{"off":None,"line":line,"edge":edge,"oracle":oracles[0]},"gold_lines":oracles}
    dump(ts(n)/"prefix.json.gz",p)
    dump(ts(n)/"ranking.json",{"line":a,"edge":b})
    dump(ts(n)/"preflight.json",item)
    print(n,approved,flush=True)
    return item
def preflight():
    ids=locked()
    with concurrent.futures.ThreadPoolExecutor(3) as pool:items=list(pool.map(prepare,ids))
    payloads={}; paths=[]
    for n in ids:
        row=get(ts(n)/"preflight.json")
        paths.extend([ts(n)/p for p in ("preflight.json","prefix.json.gz","ranking.json")])
        if not row["valid"]:continue
        s=fn(Q/"python_programs",n).read_text("utf8")
        lines="\n".join(f"{i:03d} | {line}" for i,line in enumerate(s.splitlines(),1))
        for m,adr in row["anchor"].items():
            addr="---" if adr is None else f"{adr:03d}"
            content=f"Previously ran {len(row['early'])} tests: {row['failed_early']} failed. Retained source address: {addr}.\n\nOriginal Python module (line numbers are display-only):\n"+lines
            payloads[n,m]=content
        out=ts(n)/"messages.json.gz";dump(out,{m:payloads[n,m] for m in NAMES});paths.append(out)
    dump(D/"input_lock.json",{"protocol":hf(D/"protocol_lock.json"),"eligible":[x["name"] for x in items if x["valid"]],"files":{str(p.relative_to(D)):hf(p) for p in paths}})
def eligible():
    locked();d=get(D/"input_lock.json")
    assert hf(D/"protocol_lock.json")==d["protocol"] and all(hf(D/k)==v for k,v in d["files"].items())
    return d["eligible"]
SYS='Correct the algorithm so its documented behavior holds. The original program contains a small error. A bounded earlier testing session saved at most one candidate source address; it can be absent or misleading. Inspect all code and propose one exact replacement at any location. Output only JSON {"old":"exact contiguous text from source","new":"replacement text"}, preserving exact indentation. Do not include display line numbers. Implement the general algorithm.'
def lib():
    spec=importlib.util.spec_from_file_location("shared_harness",R8/"harness.py");mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.D=D;mod.ENDPOINT="http://127.0.0.1:18931/v1/chat/completions";return mod
def infer():
    h=lib();ids=eligible();assigned={}
    for n in ids:
        prompts=get(ts(n)/"messages.json.gz");assigned[n]={}
        for m in sorted(NAMES,key=lambda k:key("r9value|"+n+"|"+k)):
            c,_=h.call(n,"repair",SYS,prompts[m],600);assigned[n][m]=c
        print(n,"generated",flush=True)
    dump(D/"assign.json",assigned);fs=[D/"assign.json",*(D/"calls").glob("*.json.gz")]
    dump(D/"answer_lock.json",{"input":hf(D/"input_lock.json"),"files":{str(p.relative_to(D)):hf(p) for p in fs}})
def answers():
    ids=eligible();lock=get(D/"answer_lock.json");assert hf(D/"input_lock.json")==lock["input"] and all(hf(D/k)==v for k,v in lock["files"].items());return ids
def patched(source,ans):
    text=ans.strip()
    text=re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$","",text).strip()
    item=json.loads(text);old,new=item["old"],item["new"]
    if not isinstance(old,str) or not isinstance(new,str) or not old or old==new or source.count(old)!=1:raise ValueError("ambiguous, absent or unchanged")
    if len(old)+len(new)>3000:raise ValueError("replacement too long")
    if re.search(r"\b(?:subprocess|pathlib|shutil|os|sys|socket|ctypes|exec|eval|compile|open|globals|locals|builtins|importlib|__\w+__|popen|system|requests|urllib|inspect|pickle|breakpoint|exit|quit|input)\b",new):raise ValueError("outside permitted algorithm operations")
    changed=source.replace(old,new,1);tr=ast.parse(changed)
    def imports(tree):return sorted(ast.dump(n) for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom)))
    if imports(tr)!=imports(ast.parse(source)):raise ValueError("imports changed")
    return changed
def grade_one(n):
    src=fn(Q/"python_programs",n).read_text("utf8");ass=get(D/"assign.json")[n];out={};cache={}
    for m in NAMES:
        k=ass[m];reply=get(D/"calls"/(k+".json.gz"))["response"]["choices"][0]["message"]["content"]
        reason=""
        try:changed=patched(src,reply)
        except (SyntaxError,TypeError,ValueError,KeyError,AttributeError) as ex:reason=str(ex)[:160];changed=src
        digest=key(changed)
        if changed==src:o=get(ts(n)/"base/testdata/outcomes.json");reuse="base"
        elif digest in cache:o,reuse=cache[digest]
        else:o,_=test(n,m,changed);reuse=None;cache[digest]=(o,m)
        out[m]={"applied":changed!=src,"reason":reason,"source_sha":digest,"reuse":reuse,"tests":o}
    dump(ts(n)/"grades.json",out)
    print(n,"graded",flush=True)
def grade():
    ids=answers()
    with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(grade_one,ids))
def cost(keys):
    c=collections.Counter()
    for k in keys:
        x=get(D/"calls"/(k+".json.gz"));u=x["response"]["usage"];c.update(calls=1,prompt=u["prompt_tokens"],output=u["completion_tokens"],seconds=sum(a["elapsed"] for a in x["attempts"]))
    return c
def report():
    ids=answers();ass=get(D/"assign.json");rows=[];sums={m:collections.Counter() for m in NAMES}
    for n in ids:
        pref=get(ts(n)/"preflight.json");gs=get(ts(n)/"grades.json");base=get(ts(n)/"base/testdata/outcomes.json")["states"]
        row={"id":n,"failed_early":pref["failed_early"],"gold_lines":pref["gold_lines"],"base":base,"heldout":pref["hold"],"arms":{}}
        for m in NAMES:
            x=gs[m];t=x["tests"];d=t["states"];full=bool(x["applied"] and t["complete"] and all(v=="passed" for v in d.values()))
            held=all(d.get(k)=="passed" for k in pref["hold"])
            v={"all_pass":full,"hold_pass":held,"applied":x["applied"],"anchor":pref["anchor"][m],"address_correct":pref["anchor"][m] in pref["gold_lines"],"complete":t["complete"],"tests_passed":sum(s=="passed" for s in d.values()),"tests":len(base),"held_passed":sum(d.get(k)=="passed" for k in pref["hold"]),"held_tests":len(pref["hold"]),"reason":x["reason"]}
            row["arms"][m]=v;sums[m].update({k:v[k] for k in ["all_pass","hold_pass","applied","address_correct","complete","tests_passed","tests","held_passed","held_tests"]});sums[m]["sum_macro_accuracy"]+=v["tests_passed"]/len(base)
        rows.append(row)
    results={"eligible":len(ids),"cohort":len(locked()),"with_prefix_failure":sum(bool(x["failed_early"]) for x in rows),"arms":{},"contrasts":{}}
    for m in NAMES:
        a=dict(sums[m]);a["mean_test_fraction"]=a.pop("sum_macro_accuracy")/len(ids);a["cost"]=cost([ass[n][m] for n in ids]);results["arms"][m]=a
    for b,m in [("off","line"),("off","edge"),("line","edge"),("off","oracle"),("edge","oracle")]:
        diff=[int(r["arms"][m]["all_pass"])-int(r["arms"][b]["all_pass"]) for r in rows];w,l=diff.count(1),diff.count(-1);u=w+l
        results["contrasts"][b+"->"+m]={"wins":w,"losses":l,"ties":len(ids)-u,"p":min(1,2*sum(math.comb(u,k) for k in range(min(w,l)+1))/2**u) if u else 1}
    results["physical"]=cost(sorted({v for a in ass.values() for v in a.values()}))
    dump(D/"rows.json",rows);dump(D/"results.json",results)
def verify():
    ids=answers();out=[D/"rows.json",D/"results.json"];old=[hf(p) for p in out];report();assert old==[hf(p) for p in out]
    for n in ids:
        p=ts(n);cases=names(fn(Q/"python_testcases","test_"+n).read_text("utf8"));visible=get(p/"prefix.json.gz");pre=get(p/"preflight.json")
        assert set(pre["early"])==set(visible) and not set(visible)&set(pre["hold"]) and set(visible)|set(pre["hold"])==set(cases)
        prompts=get(p/"messages.json.gz");assert len({re.sub(r"Retained source address: (?:---|\d+)\.","Retained source address: X.",t) for t in prompts.values()})==1
        for m,v in get(p/"grades.json").items():
            if v["applied"] and v["reuse"] is None:
                assert key(fn(p/m/"checkout/python_programs",n).read_text("utf8"))==v["source_sha"]
                assert hf(fn(p/m/"checkout/python_testcases","test_"+n))==hf(fn(Q/"python_testcases","test_"+n))
    dump(D/"verification.json",{"valid_tasks":len(ids),"source_manifest_verified":True,"messages_equal_except_address":True,"heldout_disjoint":True,"results_sha":old[1],"rows_sha":old[0]})
if __name__=="__main__":{"freeze":freeze,"preflight":preflight,"infer":infer,"grade":grade,"report":report,"verify":verify}[sys.argv[1]]()

import ast,collections,difflib,gzip,hashlib,json,os,re,subprocess,sys,time,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
D=Path(__file__).resolve().parent
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=1),encoding="utf8")
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(v):return hashlib.sha256(v.encode()).hexdigest()
def launch(work,g,args):
    return subprocess.run(args,cwd=work,env={**os.environ,"GIT_CEILING_DIRECTORIES":str(work.parent)},input=g,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=25)
def paths(patch):return {s for s in re.findall(r"(?m)^(?:--- a/|\+\+\+ b/)([^\s]+)",patch) if ".." not in s.split("/") and s.startswith("sympy/")}
def write(work,p,b):
    f=work/p
    if b is None:f.unlink(missing_ok=True)
    else:f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
def snapshot(work,ps):return {p:((work/p).read_bytes() if (work/p).exists() else None) for p in ps}
def restore(work,s):
    for p,b in s.items():write(work,p,b)
def targets(work,files,tests):
    lookup=collections.defaultdict(list)
    for p in sorted(files):
        f=work/p
        if not f.exists():continue
        s=f.read_text(encoding="utf8");tree=ast.parse(s)
        for n in tree.body:
            if isinstance(n,ast.FunctionDef):lookup[n.name].append(p+"::"+n.name)
    names=[];missing=[]
    for t in tests:
        if "::" in t:names.append(t)
        elif lookup[t]:names.extend(lookup[t])
        else:missing.append(t)
    return list(dict.fromkeys(names)),missing
def tests(work,d,tag,args,missing):
    prefix=d/tag;xml=prefix.with_suffix(".xml");log=prefix.with_suffix(".log")
    start=time.monotonic();good=[];failed=[];errors=[];skip=[]
    code=None;msg=""
    if args:
        cmd=[sys.executable,"-m","pytest","-q","--disable-warnings","-o","addopts=","--tb=short","--junitxml="+str(xml),*args]
        try:
            proc=subprocess.run(cmd,cwd=work,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"})
            code=proc.returncode;log.write_bytes(proc.stdout)
        except subprocess.TimeoutExpired as e:
            msg="timeout";log.write_bytes(e.stdout or b"")
        if xml.exists() and msg!="timeout":
            for x in ET.parse(xml).iter("testcase"):
                key=(x.get("classname","").replace(".","/")+".py::"+x.get("name",""))
                group=failed if x.find("failure") is not None else errors if x.find("error") is not None else skip if x.find("skipped") is not None else good
                group.append(key)
    return dict(requested=args,unresolved=missing,passed=good,failed=failed,errors=errors,skip=skip,code=code,time=time.monotonic()-start,complete=bool(args) and not missing and code in (0,1) and set(args)==set(good+failed) and not skip and not errors,diagnostic=msg)
def changes(s):
    return json.loads(s.strip().removeprefix(chr(96)*3+"json").removeprefix(chr(96)*3).removesuffix(chr(96)*3).strip())["edits"]
def safe(s):
    return not re.search(r"\b(?:subprocess|pathlib|shutil|os|sys|socket|ctypes|exec|eval|compile|open|globals|locals|builtins|importlib|__import__|__subclasses__|__globals__|popen|system|requests|urllib|inspect|pickle|breakpoint|exit|quit)\b",s)
def propose(work,edits,allowed):
    if not isinstance(edits,list) or not 0<len(edits)<=6:raise ValueError("bad edit count")
    new={}
    for e in edits:
        p=e["path"];old=e["old"];replacement=e["new"]
        if p not in allowed or not p.endswith(".py") or not old or not isinstance(replacement,str):raise ValueError("invalid path or edit")
        if not safe(replacement):raise ValueError("unsupported operations in generated code")
        s=new.get(p,(work/p).read_text(encoding="utf8"))
        if s.count(old)!=1 or old==replacement:raise ValueError("substring is missing, ambiguous, or unchanged")
        new[p]=s.replace(old,replacement,1)
    for s in new.values():ast.parse(s)
    return {p:s.encode() for p,s in new.items()}
def task(job):
    i,phase=job;dest=D/"tasks"/i;work=dest/"base";out=dest/"grades_v2";out.mkdir(exist_ok=True)
    g=read(dest/"grading.json");mem=read(dest/"packets.json.gz");ts=paths(g["test_patch"]);ps=paths(g["patch"])
    before=snapshot(work,ps|ts|set(mem["paths"]));test_restore={}
    try:
        a=launch(work,g["test_patch"].encode(),["git","apply","--whitespace=nowarn","-"]);assert a.returncode==0,a.stdout
        test_restore=snapshot(work,ts)
        assert any(test_restore[p]!=before[p] for p in ts),"test patch did not change files"
        wanted=["FAIL_TO_PASS","PASS_TO_PASS"];fter=g["FAIL_TO_PASS"];pter=sorted(g["PASS_TO_PASS"],key=lambda s:sha(i+"|regression|"+s))[:12]
        groups=[targets(work,ts,fter),targets(work,ts,pter)]
        if phase=="control":
            methods=["base","gold"]
        else:
            methods=["flat","evidence"]
        sigs={};details={}
        for m in methods:
            item={"applied":True,"reason":"","diff":{}}
            changed={}
            if m=="gold":
                a=launch(work,g["patch"].encode(),["git","apply","--whitespace=nowarn","-"]);assert a.returncode==0,a.stdout
                changed=snapshot(work,ps)
                assert any(changed[p]!=before[p] for p in ps),"reference patch did not change files"
                gold={p:[] for p in ps}
                for p in ps:
                    if before[p] is None or changed[p] is None:continue
                    a1=before[p].decode().splitlines();a2=changed[p].decode().splitlines()
                    for op,st,en,_,_ in difflib.SequenceMatcher(None,a1,a2,autojunk=False).get_opcodes():
                        if op!="equal":gold[p].extend(range(st+1,max(st+1,en)+1))
                item["gold_lines"]=gold
            elif m!="base":
                key=read(D/"assign.json")[i][m];item["call_id"]=key
                try:
                    reply=read(D/"calls"/(key+".json.gz"))["response"]["choices"][0]["message"]["content"];changed=propose(work,changes(reply),set(mem["paths"]))
                except (ValueError,KeyError,TypeError,SyntaxError) as e:item.update(applied=False,reason=str(e)[:260]);changed={}
                for p,b in changed.items():write(work,p,b)
            for p,b in changed.items():
                item["diff"][p]="\n".join(difflib.unified_diff((before[p] or b"").decode().splitlines(),(b or b"").decode().splitlines(),lineterm=""))
            signature=sha(json.dumps(item["diff"],sort_keys=True))
            if signature in sigs:
                item["tests"]=details[sigs[signature]]["tests"];item["reused"]=sigs[signature]
            elif not changed and phase!="control":item["tests"]=read(out/"control.json")["base"]["tests"];item["reused"]="base"
            else:item["tests"]={k:tests(work,out,m+"_"+k,*sets) for k,sets in zip(wanted,groups)}
            sigs[signature]=m;details[m]=item
            for p in changed:write(work,p,before[p])
            restore(work,test_restore)
        save(out/(phase+".json"),details);print(i,phase,[(m,x["applied"],len(x["tests"]["FAIL_TO_PASS"]["passed"])) for m,x in details.items()],flush=True)
    finally:
        restore(work,before)
if __name__=="__main__":
    phase=sys.argv[1];ids=read(D/"cohort.json")["ids"][:12]
    with ThreadPoolExecutor(max_workers=4) as executor:list(executor.map(task,[(i,phase) for i in ids if not (D/"tasks"/i/"grades_v2"/(phase+".json")).exists()]))



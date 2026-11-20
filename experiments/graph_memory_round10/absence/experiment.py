"""Locked past observations, change manifests, native replay, and pairwise decisions on disk."""
import collections,concurrent.futures,gzip,hashlib,json,os,shutil,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
from workloads import ZONES
D=Path(__file__).resolve().parent
SOURCE=D/"sources"
RT=D/"runtime"
RT.mkdir(exist_ok=True)
def get(p):return json.loads(p.read_bytes())
def enc(obj):return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha(blob):return hashlib.sha256(blob).hexdigest()
def save(p,data):
    p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(json.dumps(data,indent=2,ensure_ascii=False).encode())
def digest(p):return sha(p.read_bytes())
BASE={"tabulate":["tabulate"],"markdown-it-py":["markdown-it-py","mdurl","uc-micro-py"],"networkx":["networkx","pyparsing"],"fsspec":["fsspec"]}
OPTION={"tabulate":"wcwidth","markdown-it-py":"linkify-it-py","networkx":"pydot","fsspec":"lz4"}
TZ=[("2022.1","2022.2"),("2022.6","2022.7"),("2025.1","2025.2")]
CAND=["keep","positive","directory","negative_keys","always"]
def cases(project):return ZONES if project=="tzdata" else ["feature","normal","stdlib"]
def canon(k):return k.replace("\\","/").casefold()
def manifest(root):
    return {canon(p.relative_to(root).as_posix()):digest(p) for top in ["vendor","zones"] for p in (root/top).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
def wheel(root,rec,dest,prefix=""):
    file=SOURCE/rec["file"];assert digest(file)==rec["sha256"]
    with zipfile.ZipFile(file) as z:
        for name in z.namelist():
            if not name.startswith(prefix) or name.endswith("/"):continue
            part=Path(name[len(prefix):]);assert not part.is_absolute() and ".." not in part.parts
            out=root/dest/part;out.parent.mkdir(parents=True,exist_ok=True)
            with z.open(name) as source,out.open("wb") as sink:shutil.copyfileobj(source,sink)
def apply_inputs():
    import importlib.metadata as md
    assert all(p not in {a.metadata["Name"].lower() for a in md.distributions()} for p in ["tzdata","wcwidth","pydot","linkify-it-py","lz4","six"])
    specs=get(D/"sources.lock.json");by={(x["name"],x["version"]):x for x in specs};named={x["name"]:x for x in specs}
    jobs=[];states={}
    for project in list(BASE)+["tzdata"]:
        vals=["A","B","P"] if project!="tzdata" else [v for t in TZ for v in t]
        states[project]={}
        for val in vals:
            root=D/"states"/project/val
            for sub in ["vendor","zones"]:(root/sub).mkdir(parents=True,exist_ok=True)
            if project!="tzdata":
                for pkg in BASE[project]+([OPTION[project]] if val=="B" else ["six"] if val=="P" else []):
                    wheel(root,named[pkg],"vendor")
            else:wheel(root,by["tzdata",val],"zones","tzdata/zoneinfo/")
            states[project][val]=manifest(root)
        pairs=TZ if project=="tzdata" else [("A","B"),("A","P")]
        for old,new in pairs:
            for x,y in [(old,new),(new,old)]:
                jobs.append(dict(id=project+"_"+x+"_"+y,project=project,old=x,new=y,panel="published" if project=="tzdata" else "placebo" if "P" in [x,y] else "optional"))
    save(D/"manifest.json",states);save(D/"design.json",jobs)
    files=["PROTOCOL_RU.md","sources.lock.json","fetch.py","workloads.py","observe.py","experiment.py","design.json","manifest.json","plugin_runner.py"]
    save(D/"design.lock.json",{"files":{f:digest(D/f) for f in files},"python":sys.version,"versions":{p:md.version(p) for p in ["pytest","pytest-testmon","coverage"]}})
def locked():
    lock=get(D/"design.lock.json");assert all(digest(D/f)==s for f,s in lock["files"].items());return get(D/"design.json")
def environment(root):
    return {**os.environ,"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1","PYTHONHASHSEED":"0","PYTHONPATH":os.pathsep.join([str(root/"vendor"),str(root)])}
def observe(item):
    phase,project,val,case=item;root=D/"states"/project/val
    name=case.replace("/","_");out=D/phase/project/val/(name+".json");out.parent.mkdir(parents=True,exist_ok=True)
    proc=subprocess.run([sys.executable,"-B",str(D/"observe.py"),project,case,str(out)],env=environment(root),cwd=root,capture_output=True,timeout=45)
    if proc.returncode:raise RuntimeError((item,proc.stderr.decode(errors="replace")[-900:]))
    assert out.is_file();return out
def snapshots(phase):
    jobs=locked();target="old" if phase=="past" else "new"
    items=sorted({(phase,j["project"],j[target],case) for j in jobs for case in cases(j["project"])})
    with concurrent.futures.ThreadPoolExecutor(4) as pool:return list(pool.map(observe,items))
def module_from_path(path):
    if not path.startswith("vendor/") or ".dist-info/" in path:return None
    rel=path[len("vendor/"):]
    if rel.endswith("/__init__.py"):rel=rel[:-len("/__init__.py")]
    elif rel.endswith(".py"):rel=rel[:-3]
    elif rel.endswith((".pyd",".so")):rel=rel.rpartition("/")[0]+"/"+rel.rpartition("/")[2].split(".",1)[0];rel=rel.strip("/")
    else:return None
    ps=rel.split("/")
    return "import:"+".".join(ps) if all(p.isidentifier() for p in ps) else None
def expense(obj):
    data=enc(obj);return {"bytes":len(data),"gzip_bytes":len(gzip.compress(data,mtime=0))}
def predict():
    jobs=locked();fs=snapshots("past");man=get(D/"manifest.json");pred=[]
    for j in jobs:
        p=j["project"];a,b=[man[p][j[k]] for k in ["old","new"]]
        add=set(b)-set(a);change={k for k in a if a[k]!=b.get(k)}|add
        modules={m for k in add if (m:=module_from_path(k))}
        added_keys=modules|{"path:"+k for k in add}
        for case in cases(p):
            note=get(D/"past"/p/j["old"]/(case.replace("/","_")+".json"))
            positive=set(map(canon,note["positive"]));neg=set(map(canon,note["negative"]));dirs=set(map(canon,note["directories"]))
            hit=positive&change;matches=neg&added_keys
            any_dir=any(f.startswith(d+"/") for d in dirs for f in add)
            dec={"keep":False,"positive":bool(hit),"directory":bool(hit or any_dir),"negative_keys":bool(hit or matches),"always":True}
            pred.append({"id":j["id"],"case":case,"decision":dec,"positive_hit":sorted(hit),"negative_hit":sorted(matches),"past_result_sha":sha(enc(note["value"])),"past_contract":note["pass_test"],
                     "past_seconds":note["elapsed"],"memory":{k:expense(v) for k,v in {"positive":sorted(positive),"neg_only":sorted(neg),"negative_keys":[sorted(positive),sorted(neg)],"directory":[sorted(positive),sorted(dirs)]}.items()}})
    save(D/"forecasts.json",pred)
    save(D/"forecast.lock.json",{"forecast_sha":digest(D/"forecasts.json"),"design_sha":digest(D/"design.lock.json"),"raw":{f.relative_to(D).as_posix():digest(f) for f in fs}})
def sealed():
    jobs=locked();l=get(D/"forecast.lock.json")
    assert l["design_sha"]==digest(D/"design.lock.json") and l["forecast_sha"]==digest(D/"forecasts.json") and all(digest(D/f)==s for f,s in l["raw"].items())
    return jobs
def copy_state(src,root):
    for top in ["vendor","zones"]:
        dest=root/top;dest.mkdir(exist_ok=True)
        if (src/top).is_dir():shutil.copytree(src/top,dest,dirs_exist_ok=True)
def transition(root,src,old,new):
    for rel in set(old)-set(new):
        file=root/rel;assert file.resolve().is_relative_to(root.resolve());file.unlink()
    for rel in new:
        if new[rel]!=old.get(rel):
            dest=root/rel;dest.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(src/rel,dest)
            future=time.time()+25;os.utime(dest,(future,future))
    for top in ["vendor","zones"]:
        for directory in sorted((root/top).rglob("*"),key=lambda v:-len(v.parts)):
            if directory.is_dir() and not any(directory.iterdir()):directory.rmdir()
def plugin(j):
    p=j["project"];out=D/"plugin"/j["id"];out.mkdir(exist_ok=True,parents=True)
    oldstate=D/"states"/p/j["old"];newstate=D/"states"/p/j["new"]
    with tempfile.TemporaryDirectory(prefix="testmon-",dir=RT,ignore_cleanup_errors=True) as tmp:
        root=Path(tmp).resolve();copy_state(oldstate,root);shutil.copyfile(D/"workloads.py",root/"workloads.py")
        # One independent method per operation, stable test names and no import of the optional package during collection.
        code="from workloads import run,passed\nfrom pathlib import Path\n"
        ids={}
        for idx,case in enumerate(cases(p)):
            fname=f"test_op_{idx}";ids[case]="test_application.py::"+fname
            code+=f"\ndef {fname}():\n    v=run({p!r},{case!r},Path.cwd())\n    assert passed({p!r},{case!r},v)\n"
        (root/"test_application.py").write_text(code,encoding="utf8")
        stateinfo=get(D/"manifest.json")[p];report={}
        for stage in ["build","select"]:
            if stage=="select":
                transition(root,newstate,stateinfo[j["old"]],stateinfo[j["new"]])
                assert manifest(root)==stateinfo[j["new"]]
            target=out/(stage+".json")
            begin=time.monotonic();q=subprocess.run([sys.executable,"-B",str(D/"plugin_runner.py"),str(target)],cwd=root,env=environment(root),capture_output=True,timeout=90)
            (out/(stage+".log")).write_bytes(q.stdout+q.stderr)
            if q.returncode:raise RuntimeError((j,stage,q.stderr.decode(errors="replace")[-600:]))
            r=get(target);assert r["rc"] in [0,1,5] and (stage!="build" or set(r["executed"])==set(ids.values())),(j,stage,r)
            report[stage]={"rc":r["rc"],"cases":{k:r["executed"][nid] for k,nid in ids.items() if nid in r["executed"]},"seconds":time.monotonic()-begin,"db_bytes":r["db_bytes"],"package_metadata":r["package_metadata"]}
        save(out/"receipt.json",report)
def grade():
    jobs=sealed();snapshots("future")
    with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(plugin,jobs))
def report():
    jobs=sealed();lookup={j["id"]:j for j in jobs};allrows=[];grouped={}
    for row in get(D/"forecasts.json"):
        j=lookup[row["id"]];p=j["project"];k=row["case"];v=get(D/"future"/p/j["new"]/(k.replace("/","_")+".json"))
        plug=get(D/"plugin"/j["id"]/"receipt.json");selected=k in plug["select"]["cases"]
        same_old=plug["build"]["cases"][k]==("passed" if row["past_contract"] else "failed")
        same_new=not selected or plug["select"]["cases"][k]==("passed" if v["pass_test"] else "failed")
        assert same_old and same_new,(j,k,plug,v["pass_test"])
        a={**row,**j,"actual":v["value"],"future_contract":v["pass_test"],"changed_value":sha(enc(v["value"]))!=row["past_result_sha"],"changed_contract":row["past_contract"]!=v["pass_test"],"plugin":selected}
        a["decision"]={**row["decision"],"testmon":selected};allrows.append(a)
    for panel in ["published","optional","placebo"]:
        for direction in ["forward","reverse","both"]:
            def forward(j):
                return (j["old"],j["new"]) in TZ if panel=="published" else j["old"]=="A"
            caseset=[r for r in allrows if r["panel"]==panel and (direction=="both" or forward(r)==(direction=="forward"))]
            st={"records":len(caseset),"changed_value":sum(r["changed_value"] for r in caseset),"changed_contract":sum(r["changed_contract"] for r in caseset),"policies":{}}
            for policy in [*CAND,"testmon"]:
                st["policies"][policy]={"rerun":sum(r["decision"][policy] for r in caseset),"stale":sum(r["changed_value"] and not r["decision"][policy] for r in caseset),
                    "extra":sum(not r["changed_value"] and r["decision"][policy] for r in caseset),"stale_contract":sum(r["changed_contract"] and not r["decision"][policy] for r in caseset)}
            grouped[panel+"_"+direction]=st
    save(D/"rows.json",allrows);save(D/"results.json",grouped)
if __name__=="__main__":{"prepare":apply_inputs,"predict":predict,"grade":grade,"report":report}[sys.argv[1]]()

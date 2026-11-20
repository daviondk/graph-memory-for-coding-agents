"""Run inside Linux (WSL2 here). The Python controller never executes candidate code."""
import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = "1.0"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    temp.replace(path)


def boxed(mounts, command, cwd, stdin, limit, trace_dir, name):
    # No inherited mounts, network, processes, host environment, devices, HOME,
    # Windows interop endpoint or host drive. Nested user namespaces are disabled.
    cmd = ["bwrap","--unshare-user","--unshare-all","--disable-userns","--new-session",
           "--die-with-parent","--cap-drop","ALL","--clearenv",
           "--setenv","PATH","/usr/bin:/bin","--setenv","HOME","/tmp",
           "--setenv","LANG","C.UTF-8","--setenv","TZ","UTC",
           "--ro-bind","/usr","/usr","--ro-bind","/bin","/bin","--ro-bind","/lib","/lib",
           "--proc","/proc","--dev","/dev","--tmpfs","/tmp"]
    for access, source, dest in mounts:
        cmd.extend([access, str(source), dest])
    cmd.extend(["--chdir",cwd,"--",*command])
    start = time.monotonic()
    stdout_path = trace_dir / (name+".stdout")
    stderr_path = trace_dir / (name+".stderr")
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        try:
            p = subprocess.run(cmd, input=stdin, stdout=out, stderr=err, timeout=limit,
                               env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8"})
            code, state = p.returncode, ("ok" if not p.returncode else "nonzero")
        except subprocess.TimeoutExpired:
            code, state = None, "timeout"
    def excerpt(path):
        with path.open("rb") as f:
            size = path.stat().st_size
            if size>8192:
                f.seek(-8192,2)
            return dict(bytes=size,tail=f.read().decode("utf-8","replace"))
    return dict(state=state,returncode=code,seconds=round(time.monotonic()-start,4),
                stdout=excerpt(stdout_path),stderr=excerpt(stderr_path))


BUILDER = """import resource,sys
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
resource.setrlimit(resource.RLIMIT_CPU,(60,60))
resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
resource.setrlimit(resource.RLIMIT_NOFILE,(512,512))
sys.argv=['/builder.py']
exec(compile(open('/builder.py','rb').read(),'/builder.py','exec'),{'__name__':'__main__','__file__':'/builder.py'})
"""
CHECKER = "import sys;sys.path.insert(0,'/bench');from harness.checker_worker import main;main()"


def parse_response(path):
    if not path.is_file():
        return None,"missing_log",{}
    obj=json.loads(path.read_text(encoding="utf-8"))
    # Preserve exact builder bytes implied by a valid JSON string. No Markdown
    # stripping, quote repair, or rewriting after seeing a checker result.
    try:
        response=json.loads(obj["text"])
        if not isinstance(response,dict) or not isinstance(response.get("builder"),str) or not response["builder"].strip():
            return None,"invalid_builder",obj
        return response["builder"],"valid",obj
    except (KeyError,TypeError,json.JSONDecodeError):
        return None,"invalid_json",obj


def grade(job, args, restore):
    task, variant, key = job["task"],job["arm"],job["id"]
    is_ref = variant in ("informed","naive","noop","isolation")
    trace_dir = args.evidence / key
    trace_dir.mkdir(parents=True,exist_ok=True)
    result=dict(id=key,task=task,arm=variant,runner_version=VERSION)
    if is_ref:
        if variant=="noop":
            source, state = "pass","reference"
        elif variant=="isolation":
            source = """import os,socket
assert all(not os.path.lexists(p) for p in ['/mnt','/oracle','/bench','/root','/run','/init','/etc/resolv.conf'])
assert all(n=='lo' for _,n in socket.if_nameindex())
assert os.getcwd()=='/artifact'
assert 'WSL_INTEROP' not in os.environ
print(sorted(os.listdir('/')),socket.if_nameindex(),sorted(os.environ))"""
            state="reference"
        else:
            ref=args.repo/"tasks"/task/"reference"/(variant+".py")
            source=ref.read_text("utf-8")+"\nfrom pathlib import Path\napply(Path.cwd())\n"
            state="reference"
        response={}
    else:
        source,state,response=parse_response(args.study/"logs"/(key+".json"))
    result.update(response_state=state, model_log_keys=sorted(response), memory_words=job.get("memory_words"))
    if state=="missing_log":
        return result
    with tempfile.TemporaryDirectory(prefix="x20-action-grading-") as temporary:
        base=Path(temporary)
        artifact=base/"artifact"
        result["initial_tree_sha256"]=restore(task,artifact)
        if source is not None:
            script=base/"builder.py"
            script.write_bytes(source.encode("utf-8"))
            result["builder_sha256"]=sha(script.read_bytes())
            result["builder"]=boxed([("--bind",artifact,"/artifact"),("--ro-bind",script,"/builder.py")],
                                    ["python3","-c",BUILDER],"/artifact",None,75,trace_dir,"builder")
        else:
            result["builder"]=dict(state="not_run")
        if variant=="isolation":
            result["ok"]=result["builder"]["state"]=="ok"
            save(trace_dir/"grade.json",result)
            return result
        checker=args.repo/"tasks"/task/"checker.py"
        mounts=[("--ro-bind",artifact,"/artifact"),("--ro-bind",args.repo/"harness","/bench/harness"),
                ("--ro-bind",checker,f"/bench/tasks/{task}/checker.py"),("--ro-bind",args.repo/"oracles"/task,"/oracle")]
        request=json.dumps(dict(task_id=task,artifact="/artifact",oracle_root="/oracle")).encode()
        result["checker"]=boxed(mounts,["python3","-I","-c",CHECKER],"/tmp",request,150,trace_dir,"checker")
        c=result["checker"]
        if c["state"]!="ok":
            result.update(ok=False,verdict="checker_"+c["state"],infrastructure=True)
        else:
            parsed=json.loads(c["stdout"]["tail"].strip())
            assert parsed["checker_status"]=="completed" and isinstance(parsed["ok"],bool)
            result.update(ok=parsed["ok"],verdict=parsed["verdict"],infrastructure=False)
        if not is_ref:
            # Do not dereference candidate-provided symlinks when retaining the tree.
            with tarfile.open(trace_dir/"artifact.tar.gz","w:gz",dereference=False) as ar:
                ar.add(artifact, arcname="artifact", filter=lambda x: None if "/.git/" in x.name or x.name.endswith("/.git") else x)
        save(trace_dir/"grade.json",result)
        return result


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--repo",required=True,type=Path)
    cli.add_argument("--study",type=Path,default=HERE)
    cli.add_argument("--evidence",required=True,type=Path)
    cli.add_argument("--workers",default=4,type=int)
    cli.add_argument("--mode",choices=["canaries","model"],required=True)
    cli.add_argument("--ready-only",action="store_true")
    args=cli.parse_args()
    args.repo=args.repo.resolve()
    args.study=args.study.resolve()
    args.evidence=args.evidence.resolve()
    args.evidence.mkdir(exist_ok=True,parents=True)
    import sys
    sys.path.insert(0,str(args.repo))
    from harness.sandbox import restore
    tasks=[x.name for x in sorted((args.repo/"tasks").iterdir()) if x.is_dir() and not x.name.startswith("smoke")]
    assert len(tasks)==34
    if args.mode=="canaries":
        jobs=[dict(id=f"ref_{task}_{v}",task=task,arm=v) for task in tasks for v in ("noop","naive","informed")]
        jobs += [dict(id="sandbox_surface",task=tasks[0],arm="isolation")]
    else:
        jobs=[json.loads(s) for s in (args.study/"assigned.jsonl").read_text("utf-8").splitlines()]
        assert len(jobs)==102 and len({j["id"] for j in jobs})==102
        if args.ready_only:
            jobs=[j for j in jobs if (args.study/"logs"/(j["id"]+".json")).is_file()]
    # Reuse exact artifact/grade traces on a resumed partial run. Missing solver
    # logs are never cached. A full run reports any missing assignments explicitly.
    def run(job):
        ready=args.evidence/job["id"]/"grade.json"
        if ready.is_file():
            return json.loads(ready.read_text("utf-8"))
        return grade(job,args,restore)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results=list(pool.map(run,jobs))
    fn="canaries.jsonl" if args.mode=="canaries" else "graded.jsonl"
    path=args.study/fn
    tmp=path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in results),encoding="utf-8")
    tmp.replace(path)
    n=sum(bool(r.get("ok")) for r in results)
    print(args.mode,len(results),"cases,",n,"passes",flush=True)
    if args.mode=="canaries":
        failed=[r["id"] for r in results if r["ok"]!=(r["arm"] in ("informed","isolation")) or r.get("infrastructure") or r["builder"]["state"]!="ok"]
        print("unmatched reference expectations",failed,flush=True)
        if failed:
            raise SystemExit(1)


if __name__=="__main__":
    main()

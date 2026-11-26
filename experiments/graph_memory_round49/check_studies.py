"""Run the released study-maintainer verifiers from an independently extracted directory."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from verify_release import canon,directory,need

def worker(script):
    root=Path(__file__).resolve().parent
    need(script.is_relative_to(root),"verifier outside the extracted archive")
    marker=Path(os.environ["R49_ARCHIVE_PROJECT_ROOT"]).resolve() if os.environ.get("R49_ARCHIVE_PROJECT_ROOT") else None
    allowed=[root,Path(sys.prefix).resolve(),Path(sys.base_prefix).resolve(),Path(os.environ["TEMP"]).resolve()]
    allowed.extend(Path(p).resolve() for p in sys.path if p and Path(p).name.lower() in {"site-packages","dist-packages"})
    def guard(ev,args):
        if ev=="open" and marker and isinstance(args[0],(str,bytes,os.PathLike)):
            target=Path(os.fsdecode(args[0])).resolve()
            if target.is_relative_to(marker) and not any(target.is_relative_to(x) for x in allowed):
                raise PermissionError("external research path: "+str(target))
    sys.addaudithook(guard)
    sys.path.insert(0,str(script.parent));sys.argv=[str(script)]
    runpy.run_path(str(script),run_name="__main__")
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path(__file__).resolve().parent)
    p.add_argument("--worker",type=Path);p.add_argument("--scratch",type=Path);p.add_argument("--deny-project",type=Path)
    p.add_argument("--out",type=Path);a=p.parse_args()
    if a.worker:worker(a.worker.resolve());return
    root=a.root.resolve();register,_=directory(root);checks={}
    with TemporaryDirectory(dir=a.scratch) as tmp:
        work=Path(tmp);env={k:v for k,v in os.environ.items() if not k.startswith("PYTHON")}
        env.update(TEMP=str(work),TMP=str(work),OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",OMP_NUM_THREADS="1")
        if a.deny_project:env["R49_ARCHIVE_PROJECT_ROOT"]=str(a.deny_project)
        for study in register["studies"]:
            case=root/study
            tests=["verify.py"]+[n for n in ("verify_transfer.py","verify_candidate.py","classic/verify.py") if (case/n).is_file()]
            for name in tests:
                need((case/name).is_file(),"missing verifier: "+study)
                start=perf_counter()
                o=subprocess.run([sys.executable,"-E","-s","-B","-X","utf8",str(root/"check_studies.py"),"--worker",str(case/name)],
                    cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1200)
                detail=o.stdout.decode("utf8","replace")[-2500:]
                if o.returncode:raise RuntimeError(study+"/"+name+"\n"+detail)
                checks[study+"/"+name]=dict(exit=0,seconds=round(perf_counter()-start,3),output=detail.strip())
                print(study+"/"+name,"OK",flush=True)
    directory(root)
    if a.out:a.out.write_bytes(canon(checks))
if __name__=="__main__":main()

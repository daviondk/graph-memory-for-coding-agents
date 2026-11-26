"""Run sequential stages after the numeric inventory exists; retain elapsed wall times and CPU logs."""
import json,subprocess,sys,time
from pathlib import Path
D=Path(__file__).resolve().parent
def main():
    assert (D/"train-inventory.json").is_file()
    steps=[("fit_scale.py","fit"),("fit_scale.py","dev"),("score_scale.py","dev"),("fit_scale.py","test"),("score_scale.py","test")]
    out=[]
    for file,stage in steps:
        start=time.perf_counter()
        process=subprocess.run([sys.executable,"-X","utf8",str(D/file),stage],cwd=D,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace")
        elapsed=time.perf_counter()-start
        out.append(dict(script=file,argument=stage,returncode=process.returncode,wall_seconds=elapsed,log=process.stdout))
        (D/"run-log.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n","utf8")
        print(file,stage,round(elapsed,2),process.stdout,flush=True);process.check_returncode()
if __name__=="__main__":main()
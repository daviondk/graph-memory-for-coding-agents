"""Execute the original selected upstream Python entry point with no sockets or child processes."""
from pathlib import Path
import os,sys,runpy,shutil
from fetch import SRC
if __name__=="__main__":
    p=Path(sys.argv[1])
    assert str(p).replace("\\","/") in {"baselines/run_baseline.py","eval/run_oracle.py","eval/metrics.py"}
    def audit(event,args):
        if event in {"socket.connect","socket.getaddrinfo","subprocess.Popen","os.system"}:
            raise RuntimeError(f"Native offline path attempted {event}")
    sys.addaudithook(audit)
    for k in ["OPENAI_API_KEY","GEMINI_API_KEY","QWEN_API_KEY"]:os.environ.pop(k,None)
    os.chdir(SRC);sys.path.insert(0,str(SRC));sys.argv=[str(SRC/p)]+sys.argv[2:]
    runpy.run_path(str(SRC/p),run_name="__main__")


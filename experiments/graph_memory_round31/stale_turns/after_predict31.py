"""Run independent post-seal stages sequentially so the CPU inference queue stays within its two-thread allocation."""
import subprocess,sys,time
from base31 import D,P,Path
def run(script):
    with (P/"postprocess.log").open("a",encoding="utf8") as log:
        proc=subprocess.run([sys.executable,"-B",script],cwd=D,stdout=log,stderr=subprocess.STDOUT)
    if proc.returncode:raise RuntimeError(f"{script} exited {proc.returncode}")
def main():
    start=time.monotonic()
    while not (D/"forecast-seal.json").exists():
        if time.monotonic()-start>7200:raise TimeoutError("prediction not sealed")
        time.sleep(3)
    for script,out in (("position31.py","position-seal.json"),("score31.py","score.json"),("audit31.py","blind-audit.json"),("attainable31.py","attainable.json")):
        if not (D/out).exists():run(script)
if __name__=="__main__":main()

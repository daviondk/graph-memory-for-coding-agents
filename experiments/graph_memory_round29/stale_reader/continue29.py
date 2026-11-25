"""Run remaining sealed CPU stages serially; this process only watches the first existing actor."""
import os,subprocess,sys,time
from setup29 import D,P,save
def run(*args):
    with (P/"followup.stdout").open("a",encoding="utf8") as out:
        p=subprocess.run([sys.executable,"-B",*args],cwd=D,stdout=out,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError(f"{args[0]} failed: {p.returncode}")
def main():
    start=time.monotonic()
    while not (D/"actor-forecast-seal.json").exists():
        if time.monotonic()-start>7200:raise TimeoutError("first actor not sealed")
        time.sleep(4)
    if not (D/"prefix-forecast-seal.json").exists():run("qwen29.py","prefix")
    if not (D/"effective-actor-forecast-seal.json").exists():run("prefix_correction.py","finish")
    if not (D/"judge-input-seal.json").exists():run("judge_inputs.py")
    if not (D/"judge-forecast-seal.json").exists():run("qwen29.py","judge")
if __name__=="__main__":main()

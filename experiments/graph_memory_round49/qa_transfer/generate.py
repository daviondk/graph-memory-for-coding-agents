"""Operates only on packed prompt tokens and cryptographic receipts."""
import json
import time
from common import *
from runtime import generate,model_check

def main():
    props=model_check()
    signed=get(D/"input-seal.json");assert signed["prompts"]==sha(D/"prompts.json.gz")
    prompts=get(D/"prompts.json.gz");out={}
    log=P/("output-"+signed["prompts"]+".jsonl")
    if log.exists():
        for line in log.read_text(encoding="utf8").splitlines():
            k,p=json.loads(line);assert k in prompts and k not in out;out[k]=p
    t=time.monotonic();start_n=len(out)
    with log.open("a",encoding="utf8") as f:
        for k in sorted(prompts,key=lambda k:hexb(("r49-infer|"+k).encode())):
            if k in out:continue
            out[k]=generate(prompts[k]);f.write(json.dumps([k,out[k]],ensure_ascii=False)+"\n");f.flush()
            if (len(out)-start_n)%256==0:print("answered",len(out),len(prompts),round(time.monotonic()-t,2),flush=True)
    audit={k:generate(prompts[k]) for k in sorted(out,key=lambda k:hexb(("r49-repeat|"+k).encode()))[:32]}
    assert set(out)==set(prompts)
    put(D/"answers.json.gz",out);put(D/"replay.json",audit)
    put(D/"answer-seal.json",dict(answers=sha(D/"answers.json.gz"),audit=sha(D/"replay.json"),input=sha(D/"input-seal.json"),
        model=sha(MODEL),engine=sha(SERVER),inference=sha(Path(__file__)),client=sha(D/"runtime.py"),props=props,
        unique=len(prompts),different=sum(v!=out[k] for k,v in audit.items()),resumed=start_n,seconds=time.monotonic()-t))
    print("ANSWERS FROZEN",len(out),flush=True)
if __name__=="__main__":main()

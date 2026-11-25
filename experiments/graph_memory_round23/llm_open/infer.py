"""CPU inference. Only the accepted menu letter and numeric usage leave the private cache."""
import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from prepare import D,PRIVATE,AB,SYS,h,sha,read,write

MODEL=Path("D:/CodexResearch/x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
SERVER=Path("D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe")
MSHA="3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
def atomic(path,x):
    tmp=path.with_name(path.name+".tmp");write(tmp,x);os.replace(tmp,path)
def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
def run():
    plan=read(D/"plan-lock.json")
    assert sha(PRIVATE/"requests.json.gz")==plan["requests"] and sha(D/"menus.json.gz")==plan["menus"]
    requests=read(PRIVATE/"requests.json.gz")
    assert len(requests)==plan["unique_requests"] and sha(MODEL)==MSHA
    settings=["--device","none","--n-gpu-layers","0","--jinja","--parallel","1","--ctx-size","4096",
              "--threads","2","--threads-batch","2","--cache-ram","0"]
    identity=dict(model=MSHA,binary=sha(SERVER),settings=settings,reader=sha(Path(__file__)),sys=SYS,
                  temperature=0,seed=13,grammar="one uppercase letter within menu",max_tokens=3,plan=sha(D/"plan-lock.json"))
    cfg=h(json.dumps(identity,sort_keys=True));cache=PRIVATE/cfg;cache.mkdir(exist_ok=True)
    keys=sorted(requests,key=lambda x:h("R23-order-"+x))
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    def call(endpoint,body=None):
        req=urllib.request.Request(f"http://127.0.0.1:{port}"+endpoint,json.dumps(body).encode() if body else None,
                                   headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=150) as res:return json.load(res)
    cli=[str(SERVER),"-m",str(MODEL),"--alias","qwen-open","--host","127.0.0.1","--port",str(port),*settings]
    output={};beg=time.monotonic()
    def status(state):
        atomic(D/"progress.json",dict(status=state,done=len(output),total=len(keys),
              failed=sum(not r["ok"] for r in output.values()),updated=stamp(),config=cfg,
              elapsed_session_seconds=round(time.monotonic()-beg,3)))
    status("loading")
    with (PRIVATE/"server.log").open("ab") as log:
        proc=subprocess.Popen(cli,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                              env=dict(os.environ,CUDA_VISIBLE_DEVICES="-1",GGML_VK_VISIBLE_DEVICES=""))
        try:
            for j in range(180):
                if proc.poll() is not None:raise RuntimeError("llama server terminated before health")
                try:
                    if call("/health").get("status")=="ok":break
                except OSError:pass
                time.sleep(.5)
            else:raise RuntimeError("server did not start")
            for key in keys:
                path=cache/(key+".json")
                if path.exists():out=read(path)
                else:out={"ok":False,"attempts":[],"key":key}
                req=requests[key]
                while not out["ok"] and len(out["attempts"])<3:
                    then=time.monotonic()
                    try:
                        good=AB[:req["n"]]
                        reply=call("/v1/chat/completions",{"model":"qwen-open","messages":[{"role":"system","content":SYS},
                              {"role":"user","content":req["user"]}],"temperature":0,"seed":13,"max_tokens":3,
                              "grammar":"root ::= ["+good+"]","stream":False})
                        msg=reply["choices"][0]["message"]["content"].strip()
                        if len(msg)!=1 or msg not in good:raise ValueError("letter outside grammar")
                        usage=reply["usage"]
                        out.update(ok=True,letter=msg,prompt_tokens=usage["prompt_tokens"],completion_tokens=usage["completion_tokens"])
                        note={"outcome":"ok"}
                    except (OSError,ValueError,RuntimeError,KeyError) as e:
                        if proc.poll() is not None:raise RuntimeError("server stopped; rerun for remaining requests") from e
                        note={"outcome":"error","type":type(e).__name__,"http":getattr(e,"code",None)}
                    note["seconds"]=round(time.monotonic()-then,3);out["attempts"].append(note);atomic(path,out)
                output[key]=out;status("running")
                print(len(output),len(keys),"finished",round(time.monotonic()-beg,1),flush=True)
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
    write(D/"choices.json.gz",output)
    write(D/"reader-lock.json",dict(configuration=identity,attempts=sum(len(r["attempts"]) for r in output.values()),
         failed=sum(not r["ok"] for r in output.values()),choices=sha(D/"choices.json.gz"),n=len(output),sys=SYS))
    status("sealed")
if __name__=="__main__":run()

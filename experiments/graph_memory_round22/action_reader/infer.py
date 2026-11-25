"""Run the four-way action reader on CPU with resumable, prompt-keyed decisions."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from prepare import D,SYS,LETTERS,h,read,write
MODEL=Path("D:/CodexResearch/x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
BINARY=Path("D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe")
CACHE=Path("D:/CodexResearch/x20-observed-r-flow/action-reader")
def main():
    CACHE.mkdir(exist_ok=True)
    requests=read(D/"requests.json.gz")
    assert read(D/"selection-lock.json")["requests"]==h((D/"requests.json.gz").read_bytes())
    with MODEL.open("rb") as f:
        import hashlib
        model_sha=hashlib.file_digest(f,"sha256").hexdigest()
    assert model_sha=="3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    def call(path,body=None):
        req=urllib.request.Request(f"http://127.0.0.1:{port}"+path,data=json.dumps(body).encode() if body else None,
                                   headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
    cmd=[str(BINARY),"-m",str(MODEL),"--alias","local-4b","--host","127.0.0.1","--port",str(port),"--device","none","--n-gpu-layers","0",
         "--jinja","--parallel","1","--ctx-size","1024","--threads","3","--threads-batch","3","--cache-ram","0"]
    config=h((SYS+model_sha+str(cmd[:6])+str(cmd[9:])+h(Path(__file__).read_bytes())).encode())
    root=CACHE/config;root.mkdir(exist_ok=True)
    result={}
    with (CACHE/"server.log").open("wb") as log:
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,CUDA_VISIBLE_DEVICES="-1",GGML_VK_VISIBLE_DEVICES=""),
                              creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        try:
            for i in range(120):
                if proc.poll() is not None:raise RuntimeError("server terminated")
                try:
                    if call("/health").get("status")=="ok":break
                except OSError:pass
                time.sleep(.5)
            else:raise RuntimeError("server did not start")
            for i,(digest,msg) in enumerate(sorted(requests.items())):
                dest=root/(digest+".json")
                if not dest.exists():
                    response=call("/v1/chat/completions",{"model":"local-4b","messages":[{"role":"system","content":SYS},{"role":"user","content":msg}],
                                "temperature":0,"seed":13,"grammar":"root ::= [ABCD]","max_tokens":2,"stream":False})
                    option=response["choices"][0]["message"]["content"].strip()
                    if len(option)!=1 or option not in LETTERS:raise ValueError("inconsistent four-way response")
                    tmp=dest.with_suffix(".tmp");write(tmp,{"letter":option,"usage":response["usage"]});os.replace(tmp,dest)
                result[digest]=read(dest)
                if (i+1)%40==0:print("completed",i+1,len(requests),flush=True)
        finally:
            proc.terminate()
            try:proc.wait(10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
    write(D/"choices.json.gz",result)
    write(D/"reader-lock.json",{"responses":h((D/"choices.json.gz").read_bytes()),"n":len(result),"model":model_sha,
        "selection":h((D/"selection-lock.json").read_bytes()),"system_prompt":SYS,"decoding":"greedy, seed 13, grammar [ABCD]",
        "engine":h(BINARY.read_bytes()),"device":"CPU, 3 threads","reader":h(Path(__file__).read_bytes())})
if __name__=="__main__":main()

"""Run each independently templated input on CPU. Resume only a matching sealed input+configuration."""
import datetime, json, os, socket, subprocess, time, urllib.request
from prepare import D,PRIVATE,SYS,Path,h,sha,read,write
MODEL=Path("D:/CodexResearch/x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
SERVER=Path("D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe")
def main():
    lock=read(D/"input-lock.json");request_file=PRIVATE/"requests.json.gz"
    assert sha(request_file)==lock["requests"]
    assert sha(MODEL)=="3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
    flags=["--device","none","--n-gpu-layers","0","--jinja","--parallel","1","--ctx-size","4096","--threads","2","--threads-batch","2","--cache-ram","0"]
    cfg=dict(model=sha(MODEL),binary=sha(SERVER),flags=flags,seed=13,temperature=0,max_tokens=64,
             source=sha(Path(__file__)),system=SYS,input_lock=sha(D/"input-lock.json"))
    cfg_key=h(json.dumps(cfg,sort_keys=True));cache=PRIVATE/cfg_key;cache.mkdir(exist_ok=True)
    req=read(request_file);keys=sorted(req,key=lambda v:h("R25-delivery/"+v));out={}
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    start=time.monotonic()
    def status(state):
        write(D/"progress.json",dict(state=state,unique_done=len(out),unique_total=len(keys),attempt_failed=sum(not r["ok"] for r in out.values()),
              at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),session_seconds=round(time.monotonic()-start,3),cache=cfg_key))
    def call(endpoint,body=None):
        request=urllib.request.Request(f"http://127.0.0.1:{port}"+endpoint,data=json.dumps(body).encode() if body else None,headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request,timeout=240) as f:return json.load(f)
    status("loading")
    with (PRIVATE/"server.log").open("ab") as logfile:
        p=subprocess.Popen([str(SERVER),"-m",str(MODEL),"--alias","r25qa","--host","127.0.0.1","--port",str(port),*flags],
          stdout=logfile,stderr=subprocess.STDOUT,env=dict(os.environ,CUDA_VISIBLE_DEVICES="-1",GGML_VK_VISIBLE_DEVICES=""),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        try:
            for i in range(240):
                if p.poll() is not None:raise RuntimeError("server startup")
                try:
                    if call("/health")["status"]=="ok":break
                except OSError:pass
                time.sleep(.5)
            else:raise RuntimeError("health timeout")
            for key in keys:
                path=cache/(key+".json");r=read(path) if path.exists() else {"key":key,"ok":False,"attempts":[]}
                assert h(req[key])==key
                while not r["ok"] and len(r["attempts"])<3:
                    t=time.monotonic()
                    try:
                        ans=call("/v1/chat/completions",dict(model="r25qa",messages=[dict(role="system",content=SYS),dict(role="user",content=req[key])],
                                 temperature=0,seed=13,max_tokens=64,stream=False))
                        answer=ans["choices"][0]["message"]["content"].strip()
                        r.update(ok=True,answer=answer,finish=ans["choices"][0]["finish_reason"],**ans["usage"])
                        attempt={"outcome":"ok"}
                    except (RuntimeError,ValueError,OSError,KeyError) as e:
                        if p.poll() is not None:raise RuntimeError("server stopped; resume") from e
                        attempt={"outcome":type(e).__name__,"http":getattr(e,"code",None)}
                    attempt["seconds"]=round(time.monotonic()-t,3);r["attempts"].append(attempt);write(path,r)
                out[key]=r;status("running");print(len(out),len(keys),flush=True)
        finally:
            p.terminate()
            try:p.wait(timeout=12)
            except subprocess.TimeoutExpired:p.kill();p.wait()
    write(PRIVATE/"outputs.json.gz",out)
    public={key:{**{k:v for k,v in r.items() if k!="answer"},"answer_sha":h(r.get("answer",""))} for key,r in out.items()}
    write(D/"forecasts.json.gz",public)
    write(D/"forecast-seal.json",dict(config=cfg,forecasts=sha(D/"forecasts.json.gz"),private_outputs=sha(PRIVATE/"outputs.json.gz"),n=len(out)))
    status("sealed")
if __name__=="__main__":main()

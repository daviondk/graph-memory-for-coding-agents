"""Resumable, deterministic loopback inference on two CPU threads for independent clean messages."""
import datetime,json,os,socket,subprocess,sys,time,urllib.request
from setup29 import D,P,Path,h,sha,read,save
M=Path("D:/CodexResearch/x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf");BIN=Path("D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe")
def main(which):
    lockfile=D/(which+"-input-seal.json");info=read(lockfile);rf=P/(which+"-requests.json.gz");assert sha(rf)==info["requests"];req=read(rf)
    ms=sha(M);assert ms=="3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
    flags=["--device","none","--n-gpu-layers","0","--jinja","--parallel","1","--ctx-size","4096","--threads","2","--threads-batch","2","--cache-ram","0"]
    cfg=dict(model=ms,server=sha(BIN),cpu_args=flags,seed=13,temperature=0,max_tokens=info["max_tokens"],stage=which,
         inputs=sha(lockfile),runner=sha(Path(__file__)))
    key=h(json.dumps(cfg,sort_keys=True));cache=P/(which+"-"+key);cache.mkdir(exist_ok=True)
    keys=sorted(req,key=lambda k:h("r29-queue/"+which+k));out={};t0=time.monotonic()
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    def call(ep,data=None):
        r=urllib.request.Request(f"http://127.0.0.1:{port}"+ep,data=json.dumps(data).encode() if data else None,headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(r,timeout=240) as f:return json.load(f)
    def state(st):
        save(D/(which+"-progress.json"),dict(state=st,done=len(out),unique=len(req),failures=sum(not z["ok"] for z in out.values()),
             elapsed_current_run=round(time.monotonic()-t0,2),updated=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    state("loading")
    with (P/(which+"-server.log")).open("ab") as log:
        proc=subprocess.Popen([str(BIN),"-m",str(M),"--alias","r29-local","--host","127.0.0.1","--port",str(port),*flags],
              stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
              env=dict(os.environ,CUDA_VISIBLE_DEVICES="-1",GGML_VK_VISIBLE_DEVICES=""))
        try:
            for _ in range(200):
                if proc.poll() is not None:raise RuntimeError("llama-server startup failed")
                try:
                    if call("/health")["status"]=="ok":break
                except OSError:pass
                time.sleep(.5)
            else:raise TimeoutError("model startup")
            for k in keys:
                dst=cache/(k+".json");rr=read(dst) if dst.exists() else dict(ok=False,tries=[])
                re=req[k]
                while not rr["ok"] and len(rr["tries"])<3:
                    start=time.monotonic()
                    try:
                        fields=dict(model="r29-local",temperature=0,seed=13,max_tokens=info["max_tokens"],stream=False,
                            messages=[{"role":"system","content":re["system"]},{"role":"user","content":re["user"]}])
                        if "grammar" in re:fields["grammar"]=re["grammar"]
                        res=call("/v1/chat/completions",fields);a=res["choices"][0]["message"]["content"].strip();assert a
                        if "allow" in re and a not in re["allow"]:raise ValueError("invalid grammar result")
                        rr.update(ok=True,answer=a,finish=res["choices"][0]["finish_reason"],**res["usage"]);attempt=dict(status="ok")
                    except (AssertionError,KeyError,ValueError,OSError) as e:
                        if proc.poll() is not None:raise RuntimeError("server stopped; resume") from e
                        attempt=dict(status=type(e).__name__,http=getattr(e,"code",None))
                    attempt["s"]=round(time.monotonic()-start,3);rr["tries"].append(attempt);save(dst,rr)
                out[k]=rr;state("running")
                if len(out)%12==0:print(which,len(out),len(keys),round(time.monotonic()-t0,2),flush=True)
        finally:
            proc.terminate()
            try:proc.wait(10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
    res=P/(which+"-outputs.json.gz");save(res,out);red=D/(which+"-forecasts.json.gz")
    save(red,{k:{**{f:v for f,v in z.items() if f!="answer"},"answer_sha":h(z.get("answer",""))} for k,z in out.items()})
    save(D/(which+"-forecast-seal.json"),dict(cfg=cfg,raw=sha(res),public=sha(red),unique=len(out),failed=sum(not z["ok"] for z in out.values())))
    state("sealed")
if __name__=="__main__":main(sys.argv[1])

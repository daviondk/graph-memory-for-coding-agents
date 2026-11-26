"""Homogeneous GPU run. Called only by gpu.ps1 while it owns the shared resource mutex."""
from reference import *
import ctypes


def run():
    if os.environ.get("R39_GPU_LEASE")!="1":
        raise RuntimeError("Run gpu.ps1 to acquire the project GPU mutex.")
    assert (WORK/"graph_memory_round22/native_multiseed/official580/five-seed-results.json").exists()
    expected=read(ROOT/"panel.json")["states"]
    assert sha(CACHE/NAME)==DIGEST
    cache=CACHE/"runs-r39-gpu-v1"
    cache.mkdir(exist_ok=True)
    with gzip.open(PUB/"items.jsonl.gz","rt",encoding="utf8") as stream:
        states={r["state_id"]:r for r in map(json.loads,stream) if r["state_id"] in expected}
    assert states.keys()==expected.keys()
    s=socket.socket()
    s.bind(("127.0.0.1",0))
    port=s.getsockname()[1]
    s.close()
    args=[str(EXE),"-m",str(CACHE/NAME),"-ngl","99","-fit","off","--embeddings","--pooling","last",
          "-c","4096","-b","2048","-ub","2048","-t","3","-tb","3","-np","4","--host","127.0.0.1","--port",str(port),"--no-warmup"]
    session=requests.Session()
    session.trust_env=False
    base="http://127.0.0.1:"+str(port)
    logpath=cache/"server.log"
    log=logpath.open("wb")
    env=dict(os.environ,CUDA_VISIBLE_DEVICES="0")
    child=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,env=env)
    fingerprint={p:sha(ROOT/p) for p in ("panel.json","reference.py","gpu_reference.py","BACKENDS_RU.md","PROTOCOL_RU.md")}
    fingerprint.update(model=DIGEST,runtime=sha(EXE))
    results={}
    try:
        for attempt in range(90):
            if child.poll() is not None:
                raise RuntimeError("GPU server startup error")
            try:
                if session.get(base+"/health",timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("local GPU embeddings server")
        for q in sorted(expected,key=lambda q:expected[q]["position"]):
            name=cache/(hashlib.sha256(q.encode()).hexdigest()+".json")
            if name.exists():
                cached=read(name)
                assert cached["sign"]==fingerprint
                value=cached["data"]
            else:
                value=process_state(session,base,states[q])
                name.write_text(json.dumps({"sign":fingerprint,"state_id":q,"data":value},sort_keys=True),encoding="utf8")
            results[q]=value
            print("GPU states",len(results),"tokens",value["tokens"],"seconds",round(value["seconds"],2),flush=True)
    finally:
        child.terminate()
        child.wait(timeout=20)
        log.close()
    info=logpath.read_text(encoding="utf8",errors="replace")
    assert re_offload(info), "GPU backend not confirmed by server log"
    write("gpu-qwen-reference.json",results)
    write("gpu-forecast-seal.json",{"inputs":fingerprint,"reference":sha(ROOT/"gpu-qwen-reference.json"),
                                    "hardware":"NVIDIA GeForce RTX 3090","llama_flags":args[3:]})


def re_offload(text):
    import re
    return bool(re.search(r"offloaded (?:[1-9][0-9]*)/\d+ layers to GPU",text,re.I))


if __name__=="__main__":
    run()

from pathlib import Path
import gzip
import hashlib
import json
from contextlib import contextmanager
import socket
import subprocess
import time
import requests

D=Path(__file__).resolve().parent
R50=D.parents[1]/"graph_memory_round50"
R51=D.parents[1]/"graph_memory_round51"
CACHE=Path("D:/CodexResearch")
RUN=CACHE/"x20-r52-ce"
PANELS={"train":(R50/"semantic_address",CACHE/"x20-r50-semantic-address"),
        "2wiki":(R50/"gate_confirmation",CACHE/"x20-r50-gate-confirmation"),
        "hotpot":(R51/"routing",CACHE/"x20-r51-hotpot-routing")}
EVAL=("2wiki","hotpot")
CE=CACHE/"x20-r46-small-reranker/Qwen3-Reranker-0.6B-Q4_K_M.gguf"
READER=CACHE/"x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
EXE=CACHE/"x20-qwen38-27b/bin/llama-server.exe"
INSTRUCTION="Given a question and a passage already read, retrieve the title of the next passage needed to answer the question."
def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)
def save(path,z):
    b=(json.dumps(z,ensure_ascii=False,sort_keys=True,indent=None if path.suffix==".gz" else 2,allow_nan=False)+"\n").encode()
    path.write_bytes(gzip.compress(b,mtime=0) if path.suffix==".gz" else b)
def put(name,z):save(D/name,z)
def get(name):return read(D/name)
def session():
    s=requests.Session();s.trust_env=False;return s
@contextmanager
def server(model,settings,tag,port):
    RUN.mkdir(exist_ok=True)
    with socket.socket() as probe:probe.bind(("127.0.0.1",port))
    addr="http://127.0.0.1:"+str(port)
    cmd=[str(EXE),"-m",str(model),"--n-gpu-layers","all","--host","127.0.0.1","--port",str(port),"--no-warmup",*settings]
    with (RUN/(tag+".log")).open("wb") as log, session() as s:
        p=subprocess.Popen(cmd,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(160):
                if p.poll() is not None:raise RuntimeError("server exited: "+tag)
                try:
                    if s.get(addr+"/health",timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(.25)
            else:raise TimeoutError(tag)
            props=s.get(addr+"/props",timeout=10).json()
            assert Path(props["model_path"])==model
            apps=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,name","--format=csv,noheader"],text=True)
            assert any(r.startswith(str(p.pid)+",") and r.endswith("llama-server.exe") for r in apps.splitlines())
            yield addr,s,dict(build=props["build_info"],slots=props["total_slots"],pid=p.pid,cmd=cmd,
                device=subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version,memory.total","--format=csv,noheader"],text=True).strip(),
                template_sha=hashlib.sha256(props["chat_template"].encode()).hexdigest())
        finally:
            if p.poll() is None:p.terminate();p.wait(timeout=40)


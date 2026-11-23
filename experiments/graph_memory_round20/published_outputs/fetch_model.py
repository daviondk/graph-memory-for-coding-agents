"""Anonymous range-download of the single frozen GGUF; checksum verified before use."""
import concurrent.futures
import hashlib
import os
import time
import urllib.request
from pathlib import Path
private=Path(os.environ.get("PUBLIC_AUDIT_RUNTIME","D:/CodexResearch/x20-published-output-audit"))
name="Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
url="https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/a06e946bb6b655725eafa393f4a9745d460374c9/"+name
total=2497281120
step=8*1024*1024
bound=list(range(0,total,step))
expected="3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
d=private/"qwen-ranges"
d.mkdir(exist_ok=True,parents=True)
def pull(start):
    end=min(start+step,total)-1
    p=d/str(start)
    if p.exists() and p.stat().st_size==end-start+1:
        return
    for attempt in range(4):
        try:
            req=urllib.request.Request(url+f"?segment={start}-{end}",headers={"Range":f"bytes={start}-{end}"})
            with urllib.request.urlopen(req,timeout=35) as r:
                assert r.status==206 and r.headers["Content-Range"]==f"bytes {start}-{end}/{total}"
                b=r.read()
                assert len(b)==end-start+1
            p.write_bytes(b)
            return
        except Exception:
            if attempt==3:
                raise
            time.sleep(1+attempt)
if __name__=="__main__":
    final=private/name
    if final.exists():
        with final.open("rb") as f: assert hashlib.file_digest(f,"sha256").hexdigest()==expected
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for i,_ in enumerate(pool.map(pull,bound),1):
                if i%50==0:
                    print("checked ranges",i,"/",len(bound),flush=True)
        temp=private/(name+".assemble")
        h=hashlib.sha256()
        with temp.open("wb") as out:
            for start in bound:
                b=(d/str(start)).read_bytes()
                h.update(b)
                out.write(b)
        assert h.hexdigest()==expected
        temp.replace(final)

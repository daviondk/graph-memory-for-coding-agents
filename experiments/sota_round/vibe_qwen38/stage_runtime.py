"""Stage hash-verified Windows CUDA runtime and official llama.cpp binaries on D."""
import hashlib
import json
import shutil
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
TAG="b12441"
COMMIT="164ab018f9b7368ff8122094994c4b74e468aa0e"
FILES={"cudart-llama-bin-win-cuda-12.4-x64.zip":("8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",391443627),
       "llama-b12441-bin-win-cuda-12.4-x64.zip":("6401a8dccd4895b5c883b2df65f8e7d7d9092b857ecba38403a305b4bc14dbfd",320118864)}


def copy(name):
    h,size=FILES[name]
    path=ROOT/name
    url=f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/{name}"
    if not path.exists():
        tmp=path.with_suffix(".part")
        piece=8*1024**2
        with tmp.open("wb") as w:
            w.truncate(size)
        def region(i):
            start=i*piece
            end=min(size,start+piece)-1
            for attempt in range(5):
                req=Request(url+f"?x20piece={i}&retry={attempt}",headers={"User-Agent":"Qwen-repro-stage/1","Range":f"bytes={start}-{end}"})
                try:
                    with urlopen(req,timeout=45) as f,tmp.open("r+b") as w:
                        assert f.headers["Content-Range"]==f"bytes {start}-{end}/{size}"
                        w.seek(start)
                        data=f.read()
                        assert len(data)==end-start+1
                        w.write(data)
                    return
                except Exception:
                    if attempt==4:
                        raise
                    time.sleep(1+attempt)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(region,range((size+piece-1)//piece)))
        tmp.replace(path)
    assert path.stat().st_size==size
    with path.open("rb") as f:
        assert hashlib.file_digest(f,"sha256").hexdigest()==h
    base=ROOT/"bin"
    base.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as z:
        for member in z.infolist():
            nm=Path(member.filename).name
            if not member.is_dir() and nm.lower().endswith((".dll",".exe",".json")):
                target=base/nm
                if target.exists():
                    assert target.read_bytes()==z.read(member)
                else:
                    with z.open(member) as f, target.open("wb") as w:
                        shutil.copyfileobj(f,w)
    print("verified and extracted",name,flush=True)


if __name__=="__main__":
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(copy,FILES))
    (ROOT/"runtime_receipt.json").write_text(json.dumps({"tag":TAG,"commit":COMMIT,"assets":FILES},indent=2))

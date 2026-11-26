from pathlib import Path
import hashlib,json,platform,sys
import numpy
D=Path(__file__).resolve().parent
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def main():
    m=D/"manifest.json"
    if "--create" in sys.argv:
        files={p.name:sha(p) for p in sorted(D.iterdir()) if p.is_file() and p!=m}
        m.write_text(json.dumps({"hash":"SHA-256","python":platform.python_version(),"numpy":numpy.__version__,"files":files},indent=2)+"\n",encoding="utf8")
    info=json.loads(m.read_bytes())
    assert set(info["files"])=={p.name for p in D.iterdir() if p.is_file() and p!=m}
    for path,h in info["files"].items():assert sha(D/path)==h,path
    print("Verified",len(info["files"]),"files. Manifest SHA256",sha(m))
if __name__=="__main__":main()

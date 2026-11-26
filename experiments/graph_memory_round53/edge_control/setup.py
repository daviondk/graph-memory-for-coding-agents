from pathlib import Path
import gzip, hashlib, json, os, subprocess
D=Path(__file__).resolve().parent;R52=D.parents[1]/"graph_memory_round52";ROOT=Path("D:/CodexResearch");WORK=ROOT/"x20-r53-edge-control";DEV=ROOT/"x20-r52-wiki-directory"
SPLITS={"dev":(R52/"global_policy",DEV),"hotpot":(R52/"global_hotpot",ROOT/"x20-r52-directory-hotpot"),"2wiki":(R52/"global_confirm/large",ROOT/"x20-r52-directory-confirm-large")}
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):
    b=(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def build():
    WORK.mkdir(exist_ok=True)
    upstream=R52/"global_titles/retrieval.cpp"
    pinned=read(R52/"global_titles/prediction-seal.json")["files"]["retrieval.cpp"]
    assert pinned==sha(upstream)
    save(D/"registration.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),upstream=pinned,
        authors_kernel=sha(D/"dump.cpp"),seals={p:sha(src/"prediction-seal.json") for p,(src,_) in SPLITS.items()}))
    prog=WORK/"edge.exe"
    run=subprocess.run(["g++","-O2","-std=c++17",str(D/"dump.cpp"),"-o",str(prog)],capture_output=True);run.check_returncode()
    for p,(_,source) in SPLITS.items():
        with subprocess.Popen([str(prog),str(source)],cwd=DEV,stdout=subprocess.PIPE) as ps, gzip.open(WORK/(p+".tsv.gz"),"wb",compresslevel=3) as out:
            for b in iter(lambda:ps.stdout.read(1<<20),b""):out.write(b)
            assert ps.wait()==0
        print("Extracted",p,flush=True)
if __name__=="__main__":build()

"""Drive the published sqz executable on canonical editor responses; each task has its own native database."""
from pathlib import Path
import gzip,hashlib,json,os,re,subprocess,tempfile,time
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parent; READ=ROOT.parent/"readback"
EXE=ROOT/"vendor/sqz.exe"
REF=re.compile(r"§ref:([0-9a-f]+)(?::L(\d+)-(\d+))?§\n?\Z")
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def put(p,obj):
    text=json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=None if p.suffix==".gz" else 2).encode()
    p.write_bytes(gzip.compress(text,mtime=0) if p.suffix==".gz" else text)
def raw(v):return "".join(f"{n}\t{s}\n" for n,s in v["lines"])

def call(env,args,body=None):
    res=subprocess.run([str(EXE),*args],input=body.encode() if body is not None else None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       env=env,timeout=25,cwd=env["TEMP"],check=False)
    return {"cmd":args,"code":res.returncode,"out":res.stdout.decode(),"err":res.stderr.decode(errors="replace")}

def exercise_one(views):
    records=[];start=time.monotonic()
    with tempfile.TemporaryDirectory(dir=ROOT/"scratch") as temp:
        db=Path(temp)/"sessions.db"
        env={k:v for k,v in os.environ.items() if not k.startswith("SQZ_")}
        env.update(SQZ_DB_PATH=str(db),SQZ_QUIET="1",NO_COLOR="1",TEMP=temp,TMP=temp)
        for v in views:
            text=raw(v)
            res=call(env,["compress","--cmd","editor.view","--lossless"],text)
            ref=REF.fullmatch(res["out"])
            ex=call(env,["expand",ref[0].rstrip("\n")]) if ref else None
            records.append(dict(turn=v["turn"],path=v["path"],sha=sha(text.encode()),compression=res,expansion=ex))
        num=sum(p.stat().st_size for p in Path(temp).glob("sessions.db*"))
        assert not views or db.is_file(), (temp,views[0]["turn"])
    return dict(records=records,db_bytes=num,elapsed_s=time.monotonic()-start)

def main():
    data=load(READ/"views.gz")
    assert sha(EXE.read_bytes())==load(ROOT/"upstream.json")["exe_sha"]
    assert sha((READ/"views.gz").read_bytes())==load(READ/"input-lock.json")["files"]["views.gz"]
    names=["PROTOCOL_RU.md","exercise.py","upstream.json"]
    put(ROOT/"protocol-lock.json",dict(files={n:sha((ROOT/n).read_bytes()) for n in names},views=sha((READ/"views.gz").read_bytes())))
    (ROOT/"scratch").mkdir(exist_ok=True)
    sample=next(v for i in sorted(data) for v in data[i]["views"] if len(v["lines"])>=50 and len(raw(v))>=1000)
    positive=[dict(sample,turn=0),dict(sample,turn=1),dict(sample,turn=2,lines=sample["lines"][10:32])]
    out=exercise_one(positive);put(ROOT/"control.json",dict(source=[raw(v) for v in positive],**out))
    print("positive",[(r["compression"]["code"],str(r["compression"]["out"])[:48],r["expansion"]["out"]==raw(v) if r["expansion"] else None) for r,v in zip(out["records"],positive)],flush=True)
    ids=sorted(data)
    with ThreadPoolExecutor(6) as pool:
        outputs=dict(zip(ids,pool.map(exercise_one,[data[i]["views"] for i in ids])))
    put(ROOT/"native-receipts.gz",outputs)
    print(len(outputs),sum(len(s["records"]) for s in outputs.values()),flush=True)
if __name__=="__main__":main()

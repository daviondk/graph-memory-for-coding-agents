import json,hashlib,re,sys,urllib.request,tarfile,os,time,shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import duckdb,truststore
truststore.inject_into_ssl()
D=Path(__file__).resolve().parent
H=lambda s: hashlib.sha256(s.encode()).hexdigest()
P=Path("D:/CodexResearch/x20-round4-verified.parquet")
def save(p,obj):
    (D/p).write_text(json.dumps(obj,ensure_ascii=False,indent=1),encoding="utf8")
def main():
    con=duckdb.connect(); con.execute("select * from read_parquet(?) where repo='sympy/sympy'",[str(P)])
    names=[x[0] for x in con.description]; rows=[dict(zip(names,x)) for x in con.fetchall()]
    for q in rows:
        for k in ["FAIL_TO_PASS","PASS_TO_PASS"]:
            if isinstance(q[k],str): q[k]=json.loads(q[k])
    valid=[q for q in rows if re.fullmatch(r"1\.(?:[5-9]|1[012])",q["version"]) and q["FAIL_TO_PASS"] and all(re.fullmatch(r"(?:sympy/[\w/]+\.py::)?test_\w+",x) for x in q["FAIL_TO_PASS"]) and not re.search(r"(?i)\b(malware|exploit|vulnerabilit\w*|command injection|remote code execution)\b",q["problem_statement"])]
    selected=sorted(valid,key=lambda q:H("sym-repair-r6|"+q["instance_id"]))[:16]
    save("cohort.json",{"dataset_sha":hashlib.sha256(P.read_bytes()).hexdigest(),"sympy":len(rows),"eligible":len(valid),"ids":[q["instance_id"] for q in selected],"protocol_sha":hashlib.sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest()})
    for q in selected:
        i=q["instance_id"]; dest=D/"tasks"/i;dest.mkdir(exist_ok=True,parents=True)
        save(dest/"public.json",{k:q[k] for k in ["instance_id","repo","base_commit","problem_statement"]})
        save(dest/"grading.json",{k:q[k] for k in ["patch","test_patch","FAIL_TO_PASS","PASS_TO_PASS","version"]})
    def fetch(q):
        i=q["instance_id"];commit=q["base_commit"]; dest=D/"tasks"/i
        url="https://codeload.github.com/sympy/sympy/tar.gz/"+commit
        archive=dest/"checkout.tar.gz"
        if not archive.exists():
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(url,timeout=50) as f, open(dest/"download.tmp","wb") as w:shutil.copyfileobj(f,w)
                    os.replace(dest/"download.tmp",archive);break
                except OSError:
                    if attempt==3:raise
                    time.sleep(2)
        if not (dest/"ready.json").exists():
            with tarfile.open(archive) as tar:
                for item in tar:
                    rel=item.name.split("/",1)
                    if len(rel)<2 or not item.isfile():continue
                    p=(dest/"base"/rel[1]).resolve()
                    if not p.is_relative_to((dest/"base").resolve()):raise ValueError(p)
                    p.parent.mkdir(parents=True,exist_ok=True)
                    with tar.extractfile(item) as s,p.open("wb") as w:shutil.copyfileobj(s,w)
            save(dest/"ready.json",{"url":url,"sha256":hashlib.sha256(archive.read_bytes()).hexdigest()})
        print(i,"ready",flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,selected))
if __name__=="__main__":main()




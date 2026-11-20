"""Build base-revision source receipts without exposing labels to feature code."""
from pathlib import Path
from collections import defaultdict,Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,subprocess,sys,os,gzip,re,time,urllib.request
import pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
from prepare import ENV,DENY,write
digest=lambda b:hashlib.sha256(b).hexdigest()
read=lambda p:json.loads(gzip.decompress(p.read_bytes()))
BASEENV={**os.environ,"GIT_TERMINAL_PROMPT":"0","GCM_INTERACTIVE":"Never","GIT_ALLOW_PROTOCOL":"https"}
def run(p,args,input=None,online=False):
    return subprocess.run(["git","-c","credential.helper=","-C",str(p),*args],input=input,capture_output=True,
                          env=BASEENV if online else ENV,timeout=80)
def rows():
    loc=read(ROOT/"input/questions.json.gz")
    all_lite={json.loads(s)["instance_id"] for s in (ROOT/"input/loc_outputs.jsonl").read_text(encoding="utf8").splitlines()}
    official=ROOT.parents[1]/"sota_round/coding/verified.parquet"
    v={r["instance_id"]:r for r in pq.read_table(official,columns=["instance_id","base_commit","created_at","repo","problem_statement"]).to_pylist()}
    for x in loc:
        x["source"]="loc";x["paths"]=list(dict.fromkeys(x.pop("native")))[:5]
    transfer=[]
    for line in (ROOT/"input/river.jsonl").read_text(encoding="utf8").splitlines():
        r=json.loads(line);i=r["id"]
        if i in all_lite:continue
        m=v[i];assert m["base_commit"]==r["base_commit"] and m["repo"]==r["repo"]
        # Each source path starts with the project-store identifier, including django-s0 etc.
        paths=list(dict.fromkeys(x["source"].split("/",1)[1] for x in r["candidates"] if "/" in x["source"]))[:5]
        q=m["problem_statement"];unsafe=bool(DENY.search(q))
        transfer.append({"id":i,"source":"river","repo":m["repo"],"base":m["base_commit"],"date":str(m["created_at"]),
                         "excluded":unsafe,"question":"" if unsafe else q,"paths":paths})
    return loc+transfer
def slates(r):
    paths=r["paths"];repo=ROOT/"mirrors"/r["repo"].replace("/","__");base=r["base"]
    safe=[p for p in paths if p.endswith(".py") and not p.startswith("-") and ".." not in p.split("/")]
    if not safe or r["excluded"]:return {}
    cmd=run(repo,["ls-tree","-z","-r",base,"--",*safe])
    o={}
    if cmd.returncode==0:
        for record in cmd.stdout.split(b"\0"):
            if not record:continue
            h,n=record.split(b"\t",1);mode,kind,sha=h.split()
            if mode in (b"100644",b"100755") and kind==b"blob":
                o[n.decode("utf8","replace")]=sha.decode()
    return o
def objects(rule):
    rep,ids=rule
    if not ids:return (rep,0,0)
    repo=ROOT/"mirrors"/rep.replace("/","__")
    fo=HERE/"sources";total=0;mismatch=0
    sorted_ids=sorted(ids)
    missing=lambda: [x for x in sorted_ids if not (fo/(x+".gz")).is_file()]
    todo=missing()
    if not todo:return rep,0,0
    # Request all unique, reachable git blobs in one go per chunk (explicit public HTTPS).
    # If a mirror cannot serve a blob by SHA, try the canonical raw URL of the exact base.
    for k in range(0,len(todo),200):
        batch=todo[k:k+200]
        try:
            c=run(repo,["fetch","--quiet","--no-recurse-submodules","--no-tags","--no-write-fetch-head","--stdin",
                        "https://github.com/"+rep+".git"],input=("\n".join(batch)+"\n").encode(),online=True)
        except subprocess.TimeoutExpired:
            pass
    cp=run(repo,["cat-file","--batch"],input=("\n".join(todo)+"\n").encode())
    import io
    f=io.BytesIO(cp.stdout)
    for oid in todo:
        header=f.readline().split()
        if len(header)==2:continue
        if len(header)!=3:break
        key,kind,size=header
        assert key.decode()==oid
        value=f.read(int(size));assert f.read(1)==b"\n"
        if len(value)>2_000_000:continue
        assert hashlib.sha1(b"blob "+str(len(value)).encode()+b"\x00"+value).hexdigest()==oid
        (fo/(oid+".gz")).write_bytes(gzip.compress(value,mtime=0));total+=1
    for oid in missing():
        base,path=ids[oid];url="https://raw.githubusercontent.com/"+rep+"/"+base+"/"+urllib.parse.quote(path)
        try:
            with urllib.request.urlopen(url,timeout=9) as body: b=body.read(2_000_001)
            if len(b)>2_000_000:continue
            assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\x00"+b).hexdigest()==oid
            (fo/(oid+".gz")).write_bytes(gzip.compress(b,mtime=0));total+=1
        except Exception:mismatch+=1
    print("fetched",rep,total,"missing",mismatch,flush=True)
    return rep,total,mismatch
def main():
    roster=rows()
    (HERE/"sources").mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=5) as ex:found=list(ex.map(slates,roster))
    grouped=defaultdict(dict)
    for r,m in zip(roster,found):
        r["blobs"]=m
        for file,oid in m.items():grouped[r["repo"]][oid]=(r["base"],file)
    write(HERE/"inputs.json.gz",roster)
    print("roster",len(roster),"paths",sum(len(r["paths"]) for r in roster),
          "resolved",sum(map(len,found)),"unique",sum(len(v) for v in grouped.values()),flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:receipts=list(ex.map(objects,sorted(grouped.items())))
    meta={"input_sha256":digest((HERE/"inputs.json.gz").read_bytes()),"protocol":digest((HERE/"PROTOCOL.md").read_bytes()),
          "river_source":digest((ROOT/"input/river.jsonl").read_bytes()),"rosters":dict(Counter(r["source"] for r in roster)),
          "missing":[[r["id"],p] for r in roster for p,o in r["blobs"].items() if not (HERE/"sources"/(o+".gz")).exists()],
          "instance_path_resolution":dict(Counter(len(r["paths"])-len(r["blobs"]) for r in roster)),
          "stored_unique_files":len(list((HERE/"sources").glob("*.gz"))),"request_results":receipts}
    (HERE/"source_receipt.json").write_text(json.dumps(meta,indent=2),encoding="utf8")
if __name__=="__main__":main()


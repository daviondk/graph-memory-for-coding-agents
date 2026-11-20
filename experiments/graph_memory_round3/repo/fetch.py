"""Download publisher-hosted parquet and author tokenizer by pinned revisions; no dataset scripts run."""
import concurrent.futures, hashlib, json, pathlib, urllib.request, time
D=pathlib.Path(__file__).resolve().parent
REV="c9daeba525cb28cfb9fbe17886f32b8ea34fc870"
API="https://huggingface.co/api/datasets/tianyang/repobench-r/tree/"+REV+"?recursive=true"
def main():
    out=D/"inputs";out.mkdir(exist_ok=True)
    items=json.load(urllib.request.urlopen(API,timeout=60))
    files=[o for o in items if o['path'].startswith('python_') and ("/test_" in o["path"] or "/train_hard/0000" in o["path"]) and o["path"].endswith(".parquet")]
    def fetch(o):
        rel=o["path"];p=out/rel.replace("/","_");u="https://huggingface.co/datasets/tianyang/repobench-r/resolve/"+REV+"/"+rel
        h=o["lfs"]["oid"]
        if not p.exists() or hashlib.file_digest(p.open("rb"),"sha256").hexdigest()!=h:
            for i in range(4):
                try:
                    with urllib.request.urlopen(u,timeout=100) as src,p.with_suffix(".part").open("wb") as dst:
                        while chunk:=src.read(1024*1024):dst.write(chunk)
                    assert hashlib.file_digest(p.with_suffix(".part").open("rb"),"sha256").hexdigest()==h
                    p.with_suffix(".part").replace(p);break
                except Exception:
                    if i==3:raise
                    time.sleep(2)
        print(p.name,o["size"],flush=True);return {"path":p.name,"url":u,"sha256":h,"bytes":o["size"]}
    with concurrent.futures.ThreadPoolExecutor(4) as ex:result=list(ex.map(fetch,files))
    (D/"sources.json").write_text(json.dumps(result,indent=1),encoding="utf8")
if __name__=="__main__":main()

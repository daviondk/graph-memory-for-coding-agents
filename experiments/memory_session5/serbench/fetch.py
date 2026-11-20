"""Download public pinned SDK and data with independent Git blob verification."""
import concurrent.futures, hashlib, json, pathlib, urllib.request, time
ROOT=pathlib.Path(__file__).resolve().parent
COMMIT="8c27a88e48dcbcd4a5745573c95937a4740f4406"
remote="https://raw.githubusercontent.com/LordTARN1SHED/SERBench/"+COMMIT+"/"
def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(url,timeout=65) as stream:return stream.read()
        except OSError:
            if i==3:raise
            time.sleep(i+1)
def main():
    tree=json.loads(get("https://api.github.com/repos/LordTARN1SHED/SERBench/git/trees/"+COMMIT+"?recursive=1"))["tree"]
    names={"data/cal500/items.jsonl.gz","data/cal500/labels.jsonl.gz","data/test500/items.jsonl.gz","data/manifest.json","LICENSE","DATA_LICENSE.md","THIRD_PARTY_NOTICES.md","docs/EVALUATION.md","docs/DATASET.md"}
    selected=[r for r in tree if r["path"] in names or (r["path"].startswith("src/serbench/") and r["path"].endswith(".py"))]
    def download(row):
        name=row["path"];path=ROOT/"upstream"/name;path.parent.mkdir(exist_ok=True,parents=True)
        raw=path.read_bytes() if path.exists() else get(remote+name)
        git_hash=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        assert git_hash==row["sha"],(name,len(raw),git_hash,row["sha"])
        if not path.exists():path.write_bytes(raw)
        return {"file":name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"blob":git_hash}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:receipts=list(pool.map(download,selected))
    (ROOT/"source.json").write_text(json.dumps({"commit":COMMIT,"url":remote,"files":receipts},indent=2))
if __name__=="__main__":main()

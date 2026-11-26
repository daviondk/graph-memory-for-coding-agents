"""Prepare distinct blind observations and labels for the two-support experiment."""
import gzip,hashlib,json,subprocess
from pathlib import Path
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent
PRIVATE=Path("D:/CodexResearch/x20-r31-hotpot")
REV="1908d6afbbead072334abe2965f91bd2709910ab"
URL=f"https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/{REV}/distractor/validation-00000-of-00001.parquet"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
    raw=(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def main():
    PRIVATE.mkdir(exist_ok=True);path=PRIVATE/"validation.parquet"
    if not path.exists():
        temp=PRIVATE/"download.tmp"
        subprocess.run(["curl.exe","--fail","--location","--silent","--show-error","--retry","2","--max-time","200","-o",str(temp),URL],check=True)
        temp.replace(path)
    blind={};labels={}
    for r in pq.read_table(path).to_pylist():
        q=r["id"];c=r["context"];f=r["supporting_facts"]
        assert q not in blind and len(c["title"])==len(c["sentences"])
        blind[q]={"q":r["question"],"titles":c["title"],"sentences":c["sentences"]}
        labels[q]={"support":sorted(set(f["title"])),"type":r["type"]}
    put(PRIVATE/"blind.json.gz",blind);put(PRIVATE/"labels.json.gz",labels)
    put(ROOT/"source.json",{"url":URL,"revision":REV,"parquet_sha":sha(path),"questions":len(blind),
       "observations":sha(PRIVATE/"blind.json.gz"),"labels":sha(PRIVATE/"labels.json.gz"),"projector":sha(Path(__file__))})
if __name__=="__main__":main()

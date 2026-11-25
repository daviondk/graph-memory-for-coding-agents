import gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round25/directional_open"
P=Path("D:/CodexResearch/x20-r25-squad");TRAIN=P/"train-v1.1.json";DEV=P/"dev-v1.1.json"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,r):
    b=(json.dumps(r,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False)+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b);return sha(p)
def freeze():
    k={"before_new_cohort_and_outcomes":True,"source":"https://rajpurkar.github.io/SQuAD-explorer/dataset/train-v1.1.json","baseline":sha(R/"manifest.json"),"protocol":sha(D/"PROTOCOL_RU.md"),"prior_dev_sha":sha(DEV),"seed":263117,"B":20000,"P":100000}
    p=D/"plan.json"
    if p.exists():assert read(p)==k
    else:save(p,k)
if __name__=="__main__":freeze();print(sha(D/"plan.json"))

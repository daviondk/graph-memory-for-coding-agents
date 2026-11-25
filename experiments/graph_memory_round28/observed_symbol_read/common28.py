from pathlib import Path
import json,gzip,hashlib
D=Path(__file__).resolve().parent
W=D.parents[1];R=W/"graph_memory_round27/code_boundary"
P=Path("D:/CodexResearch/x20-r28-symbols")
V=Path("D:/CodexResearch/x20-r27-code-data/verified.parquet")
S=V.parent/"swe-explore.jsonl"
B=Path("D:/CodexResearch/x20-r8-swerank-runtime/locbench-test-c44cf3b74e07ca642cec841b471a9939907c12a7.parquet")
T=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def save(p,x):
    b=(json.dumps(x,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
    return sha(p)
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def checks():
    req={V:"a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd",S:"dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202",B:"8df0833c2c1276c5837aab923d489ab97d7654529abe759d0f59242c4978a662",T:"d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",D/"PROTOCOL_RU.md":"0bffdc0757e8ae991a484ea8898048f7a05837ce3d4f184260f599f2b487cc52"}
    for p,h in req.items():assert sha(p)==h,p


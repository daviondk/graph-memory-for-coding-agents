from pathlib import Path
import json, gzip, hashlib
D=Path(__file__).resolve().parent
P=Path("D:/CodexResearch/x20-r27-code-data")
T=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def save(p, o):
    data=(json.dumps(o,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix==".gz" else data)
    return sha(p)
def read(p): return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def inputs():
    assert sha(P/"verified.parquet")=="a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd"
    assert sha(P/"swe-explore.jsonl")=="dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202"
    assert sha(D/"PROTOCOL_RU.md")=="94a63bf0030bf81c11d10a6c2f31d593062c3938028e8a5ce346a7a4b149c8be"


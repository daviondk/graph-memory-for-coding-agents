import gzip,hashlib,json,os
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parents[1]
PRIVATE=Path('D:/CodexResearch/x20-r46-reader-transfer')
RAW=PRIVATE/'musique-train.jsonl'
DEV=Path('D:/CodexResearch/x20-r32-musique/musique.jsonl')
AUTHOR=DEV.parent/'author'
SERVER=Path('D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe')
MODEL=Path('D:/CodexResearch/x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf')
PORT=18864
ARMS=('expanded','mention_expanded','title','mention_title')
def hexb(b):return hashlib.sha256(b).hexdigest()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def get(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def put(p,v):
    b=(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
    temp=p.with_name(p.name+'.new');temp.write_bytes(gzip.compress(b,mtime=0) if p.suffix=='.gz' else b);os.replace(temp,p)

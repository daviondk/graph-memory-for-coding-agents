from pathlib import Path
import gzip,hashlib,json,datetime
D=Path(__file__).resolve().parent
R4=D.parents[1]/"graph_memory_round4";R=R4/"repo";E=R4/"encoder"
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(x):return hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
def filehash(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rr(p):
    with gzip.open(p,'rt',encoding='utf8') as f:yield from map(json.loads,f)
def dump(n,obj):(D/n).write_text(json.dumps(obj,ensure_ascii=False,indent=1,default=lambda x:x.item()),encoding='utf8')
def load(p):return json.loads(Path(p).read_bytes())
def jsonrows(p,rows):
    with gzip.open(D/p,'wt',encoding='utf8',compresslevel=5) as f:
        for row in rows:f.write(json.dumps(row,separators=(',',':'),ensure_ascii=True)+'\n')


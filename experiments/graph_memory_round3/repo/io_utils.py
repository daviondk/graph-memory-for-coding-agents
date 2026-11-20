import hashlib, json, gzip, pathlib, datetime
import numpy as np
D=pathlib.Path(__file__).resolve().parent
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,data):(D/name).write_text(json.dumps(data,ensure_ascii=False,indent=1),encoding="utf8")
def read(name):return json.loads((D/name).read_bytes())
def dump(f,v):f.write(json.dumps(v,separators=(',',':'),ensure_ascii=True)+'\n')
def load_gz(p):
    with gzip.open(p,'rt',encoding="utf8") as f:
        for l in f:yield json.loads(l)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

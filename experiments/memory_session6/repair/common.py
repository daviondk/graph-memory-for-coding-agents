import hashlib, json, pathlib, gzip, os, datetime
ROOT = pathlib.Path(__file__).resolve().parent
def sha(data):
    return hashlib.sha256(data if isinstance(data,bytes) else data.encode()).hexdigest()
def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(',', ':'))
def save(name,obj):
    p=ROOT/name
    p.parent.mkdir(parents=True,exist_ok=True)
    data=canonical(obj).encode()
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_bytes(gzip.compress(data,mtime=0) if p.suffix=='.gz' else data)
    os.replace(temp,p)
def read(name):
    p=ROOT/name
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
def subset_hash(names):
    return {n:sha((ROOT/n).read_bytes()) for n in sorted(names)}
def check(lock):
    assert subset_hash(lock.keys())==lock
def path(i,filename):
    return f'tasks/{i}/{filename}'


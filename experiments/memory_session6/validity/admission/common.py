import pathlib,gzip,json,hashlib,datetime,math,csv
ROOT=pathlib.Path(__file__).resolve().parent
INPUT=ROOT.parent/'exposure.jsonl.gz'
def digest(s):return hashlib.sha256(s if isinstance(s,bytes) else s.encode()).hexdigest()
def canon(x):return json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(',',':'))
def write(n,d): (ROOT/n).write_bytes(canon(d).encode())
def read(n):return json.loads((ROOT/n).read_bytes())
def rows(p):
    with gzip.open(p,'rt',encoding='utf8') as f:
        for line in f:yield json.loads(line)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def hashes(names):return {n:digest((ROOT/n).read_bytes()) for n in names}
def sourcecheck():
    l=read('design_lock.json');assert digest(INPUT.read_bytes())==l['source_sha'] and hashes(l['hashes'])==l['hashes']
NAMES=('never','lru','lfu','twohit','edit_twohit','bottomk')
def splitmap():
    repos={r['repo'] for r in rows(INPUT)}
    return {k:('A' if j%2==0 else 'B') for j,k in enumerate(sorted(repos,key=lambda x:digest('admit-split6|'+x)))}


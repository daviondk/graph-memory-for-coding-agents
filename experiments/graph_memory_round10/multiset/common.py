import base64,hashlib,json,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parent
R9=ROOT.parents[1]/'graph_memory_round9'
PANELS=['testmemory_compat','testmemory_holdout']
ARMS=['r9','bucket','flat_bloofi','sparse_dict','xor_map','old_selector']
def load(path):
    if path.suffix=='.gz':
        with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)
    return json.loads(path.read_bytes())
def put(path,obj):
    data=json.dumps(obj,ensure_ascii=False,indent=None if path.suffix=='.gz' else 1,separators=(',',':')).encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(data,compresslevel=4,mtime=0) if path.suffix=='.gz' else data)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def locks(files):
    return {p.relative_to(ROOT).as_posix():sha(p) for p in files}
def verify(values):
    assert all(sha(ROOT/p)==v for p,v in values.items()),'Digest mismatch'

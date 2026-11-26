from pathlib import Path
import gzip,hashlib,json,sys
D=Path(__file__).resolve().parent;W=D.parents[1]
S=W/"graph_memory_round41/structural_invalidation";G=W/"graph_memory_round40/guarded_updates"
RAW=Path("D:/CodexResearch/x20-r31-handoff");V=W/"graph_memory_round38/edit_ready"
sys.path.insert(0,str(S))
from shared import case_id, signed, sha, h, read, select

def save(name,obj):
    p=D/name;b=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if name.endswith(".gz") else b)


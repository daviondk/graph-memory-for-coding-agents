"""Dataset constants, immutable JSON records and deterministic AST alignment."""
import ast
import collections
import gzip
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent
OLD="9005642440e1479dd26c2c5d64c27f596445aaac"
NEW="992a58c1036fcf4d52cbf3313b6217b7c07b11d9"
MODULES=("dictutils","formatutils","iterutils","listutils","mathutils","namedutils","queueutils","setutils","statsutils","strutils","tableutils","timeutils","typeutils")
OP={"Lt":"LtE","LtE":"Lt","Gt":"GtE","GtE":"Gt"}
def stable(obj):return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf8")
def h(data):return hashlib.sha256(data).hexdigest()
def key(s):return h(("r19-boundary|"+s).encode())
def put(path,obj):
    if isinstance(path,str):path=D/path
    b=stable(obj)+b"\n"
    if path.suffix==".gz":b=gzip.compress(b,mtime=0)
    if path.exists():assert path.read_bytes()==b,path
    else:path.write_bytes(b)
def get(path):
    if isinstance(path,str):path=D/path
    raw=path.read_bytes();return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)
def inventory(repo):
    found={}
    for m in MODULES:
        file=repo/"boltons"/(m+".py")
        if not file.exists():continue
        body=ast.parse(file.read_bytes());dupes=collections.Counter()
        def visit(node,parents=()):
            if isinstance(node,ast.While):return
            if isinstance(node,(ast.FunctionDef,ast.ClassDef,ast.AsyncFunctionDef)):parents=(*parents,(node.name,type(node)))
            if isinstance(node,ast.Compare) and any(t in (ast.FunctionDef,ast.AsyncFunctionDef) for _,t in parents) and len(node.ops)==1 and type(node.ops[0]).__name__ in OP:
                name=m+"."+".".join(a for a,_ in parents);expr=ast.dump(node,include_attributes=False)
                fingerprint=name+"|"+h(expr.encode())[:20];dupes[fingerprint]+=1
                site=fingerprint+"|"+str(dupes[fingerprint])
                found[site]={"module":m,"function":name,"expression":ast.unparse(node),"op":type(node.ops[0]).__name__,"line":node.lineno,"column":node.col_offset}
            for child in ast.iter_child_nodes(node):visit(child,parents)
        visit(body)
    return found
def sites(a,b):
    old=inventory(a);new=inventory(b);counts=collections.Counter();kept=[]
    for s in sorted(set(old)&set(new),key=key):
        f=old[s]["function"]
        if counts[f]>=2:continue
        counts[f]+=1
        kept.append({"id":s,"old":old[s],"new":new[s]})
    return kept[:48],{"old_sites":len(old),"new_sites":len(new),"common_sites":len(set(old)&set(new)),"after_two_per_function":len(kept)}

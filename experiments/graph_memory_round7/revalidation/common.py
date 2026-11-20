"""Static query and observation definitions shared by the predictor and independent scorer."""
import ast
import hashlib
import io
import json
import re
import tokenize
import zipfile
from collections import Counter
from pathlib import Path
from functools import lru_cache

ROOT=Path(__file__).resolve().parent
CACHE=Path("D:/CodexResearch/x20-round7-wheel-cache")
POLICIES=("file","always_reuse","caller","dependencies","headers")
def digest(data):
    return hashlib.sha256(data).hexdigest()
def fingerprint(value):
    return digest(json.dumps(value,sort_keys=True,separators=(",",":")).encode())
def modules(wheel):
    with zipfile.ZipFile(CACHE/wheel) as archive:
        return {p:archive.read(p) for p in archive.namelist() if p.endswith(".py") and
                not any(x in {"test","tests","testing","_vendor","vendor","third_party","__pycache__"} or
                        x.startswith("test_") or x.endswith((".dist-info",".data")) for x in p.lower().split("/"))}
def decode(data):
    enc,_=tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(enc)
def header_ends(source):
    ends={}
    start=None
    depth=0
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if start is None:
            if tok.type==tokenize.NAME and tok.string=="def":
                start=tok.start[0]
                depth=0
        elif tok.type==tokenize.OP:
            if tok.string in ("(","[","{"):
                depth+=1
            elif tok.string in (")","]","}"):
                depth-=1
            elif tok.string==":" and depth==0:
                ends[start]=tok.end[0]
                start=None
    return ends
class Calls(ast.NodeVisitor):
    def __init__(self):
        self.names=set()
    def visit_Call(self,node):
        if isinstance(node.func,ast.Name):
            self.names.add(node.func.id)
        self.generic_visit(node)
    def visit_FunctionDef(self,node):pass
    visit_AsyncFunctionDef=visit_FunctionDef
    visit_ClassDef=visit_FunctionDef
    visit_Lambda=visit_FunctionDef
@lru_cache(maxsize=150)
def analyze(data):
    source=decode(data)
    tree=ast.parse(source)
    funcs=[f for f in tree.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))]
    frequency=Counter(f.name for f in funcs)
    ends=header_ends(source)
    defs={f.name:f for f in funcs if frequency[f.name]==1}
    result={}
    for name,f in defs.items():
        signature=fingerprint([type(f).__name__,ast.dump(f.args),ast.dump(f.returns) if f.returns else None,
                               [ast.dump(param) for param in getattr(f,"type_params",())]])
        visitor=Calls()
        for child in f.body: visitor.visit(child)
        result[name]=dict(full=(f.lineno,f.end_lineno),head=(f.lineno,ends[f.lineno]),sig=signature,
                          calls=sorted((visitor.names & defs.keys())-{name}))
    return result
def answer(defs,name):
    if name not in defs:return None
    return fingerprint([(t,defs[t]["sig"]) for t in defs[name]["calls"]])
def dump(path,rows):
    (ROOT/path).write_text(json.dumps(rows,indent=2,ensure_ascii=False)+"\n",encoding="utf8")

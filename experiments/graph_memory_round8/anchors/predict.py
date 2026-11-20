"""Read old method memories and rank current candidates. No post-edit annotation is loaded."""
import ast
import collections
import functools
import gzip
import hashlib
import io
import json
import keyword
import tokenize
import warnings
from prepare import ROOT,git,hashbytes,load,save
warnings.filterwarnings("ignore",category=SyntaxWarning)
def stable_gzip(name,data):
    (ROOT/name).write_bytes(gzip.compress(data,compresslevel=7,mtime=0))
def tag(method):
    return (method["path"],method["qual"],method["line"])
def locate(methods,name,ctx):
    ctx=ctx.removesuffix(".__module__").strip(".").split(".")
    found=[]
    for idx,m in enumerate(methods):
        if m["name"]!=name:continue
        mod=m["path"][:-3].split("/")
        for path in [mod,mod[:-1] if mod[-1]=="__init__" else mod]:
            scope=path+m["qual"].split(".")[:-1]
            if scope[-len(ctx):]==ctx:
                found.append(idx);break
    return found
@functools.lru_cache(maxsize=120000)
def fingerprint(tokens):
    return int.from_bytes(hashlib.blake2b("\0".join(tokens).encode(),digest_size=8,person=b"R8Code").digest(),"big")
def grams(seq):
    if not seq:return frozenset()
    if len(seq)<5:return frozenset([fingerprint(tuple(seq))])
    return frozenset(fingerprint(tuple(seq[i:i+5])) for i in range(len(seq)-4))
def representations(nd):
    body=nd.body
    if body and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str):
        body=body[1:]
    source="\n".join(ast.unparse(stmt) for stmt in body)
    lex=[];shape=[]
    for t in tokenize.generate_tokens(io.StringIO(source).readline):
        if t.type not in (tokenize.NAME,tokenize.NUMBER,tokenize.STRING,tokenize.OP):continue
        lex.append(t.string)
        kind=t.string
        if t.type==tokenize.NAME and not keyword.iskeyword(t.string):kind="<id>"
        if t.type==tokenize.NUMBER:kind="<num>"
        if t.type==tokenize.STRING:kind="<str>"
        shape.append(kind)
    return (grams(lex),grams(shape))
@functools.lru_cache(maxsize=110)
def parse_blob(project,oid):
    try:
        tree=ast.parse(git(project,"cat-file","blob",oid))
    except (SyntaxError,UnicodeError,ValueError):
        return (),False
    methods=[]
    def visit(n,parents):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            methods.append(dict(name=n.name,qual=".".join((*parents,n.name)),line=n.lineno,end=n.end_lineno,grams=representations(n)))
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            parents=(*parents,n.name)
        for c in ast.iter_child_nodes(n):visit(c,parents)
    visit(tree,())
    return tuple(methods),True
def front(project,old,new):
    raw=git(project,"diff","--raw","--no-abbrev","--no-renames","-z",old,new,"--","*.py").split(b"\0")
    prev=[];curr=[];stats=collections.Counter()
    for meta,encoded_path in zip(raw[::2],raw[1::2]):
        if not meta:continue
        _,_,a,b,_=meta.decode().split()
        path=encoded_path.decode("utf8")
        if any(x in path.lower() for x in ("vulnerab","exploit","malware","secret_key_agreement")):continue
        for oid,dest,side in ((a,prev,"old"),(b,curr,"current")):
            if not oid.strip("0"):continue
            ms,ok=parse_blob(project,oid)
            stats[side+"_files"]+=1
            stats[side+"_parse_failure"]+=int(not ok)
            for m in ms:dest.append(dict(m,path=path))
    return prev,curr,dict(stats)
def predict(src,others,targets):
    lx,sh=src["grams"]
    rare=[]
    for i in (0,1):
        counts=collections.Counter(g for m in others for g in m["grams"][i])
        rare.append(sorted(src["grams"][i],key=lambda g:(counts[g],g)))
    keys={
        "minlex":(sorted(lx)[:8],[]),"rarelex":(rare[0][:8],[]),"shape":([],rare[1][:8]),
        "mixed":(rare[0][:4],rare[1][:4])
    }
    tie=[]
    for m in targets:
        same=m["path"]==src["path"]
        owner=m["qual"].rpartition(".")[0]==src["qual"].rpartition(".")[0]
        tie.append((int(m["name"]!=src["name"]),int(not same),int(not owner),abs(m["line"]-src["line"]) if same else 10**9,tag(m)))
    scored={"address":[0]*len(targets)}
    for arm,(a,b) in keys.items():
        a,b=set(a),set(b)
        scored[arm]=[len(a&u["grams"][0])+len(b&u["grams"][1]) for u in targets]
    scored["full"]=[len(lx&m["grams"][0])/max(1,len(lx|m["grams"][0])) for m in targets]
    orders={k:sorted(range(len(targets)),key=lambda i:(-v[i],tie[i])) for k,v in scored.items()}
    # Retain each mixed score for the missing-successor stress test.
    return orders,scored["mixed"],{k:8*(len(a)+len(b)) for k,(a,b) in keys.items()}|{"full_hash_bytes":8*len(lx)}
def main():
    by=collections.defaultdict(list)
    for r in load("queries.json"):by[r["project"],r["old"],r["new"]].append(r)
    pool={};rows=[];skipped=[]
    for (project,old,new),qs in by.items():
        prev,curr,stats=front(project,old,new)
        pool[new]=dict(project=project,stats=stats,candidates=[tag(m) for m in curr])
        for q in qs:
            ix=locate(prev,q["name"],q["scope"])
            if len(ix)!=1:
                skipped.append(dict(case=q["case"],old_matches=len(ix)));continue
            src=prev[ix[0]]
            orders,v,payload=predict(src,[m for m in prev if m["path"]==src["path"]],curr)
            rows.append(dict(case=q["case"],commit=new,project=project,origin=tag(src),rankings=orders,
                             mixed_scores=v,bytes=payload))
    stable_gzip("pools.json.gz",json.dumps(pool,separators=(",",":")).encode())
    stable_gzip("rankings.jsonl.gz",("\n".join(json.dumps(x,separators=(",",":")) for x in rows)+"\n").encode())
    save("skips.json",skipped)
    locknames=["PROTOCOL.md","prepare.py","predict.py","score.py","queries.json","pools.json.gz","rankings.jsonl.gz","skips.json"]
    save("prediction-lock.json",{x:hashbytes((ROOT/x).read_bytes()) for x in locknames})
    print(len(rows),"predictions;",len(skipped),"unresolved old sources",flush=True)
if __name__=="__main__":main()

"""Read-only syntactic projection of Java source with tree-sitter."""
from functools import lru_cache
import sys
from common import *
sys.path.insert(0,str(CACHE/"python"))
from tree_sitter import Language,Parser
import tree_sitter_java

PARSER=Parser(Language(tree_sitter_java.language()))
OWNERS={"class_declaration","interface_declaration","enum_declaration","record_declaration","annotation_type_declaration"}
METHOD={"method_declaration","constructor_declaration"}
SKIP={"block_comment","line_comment"}
def text(n):
    return n.text.decode("utf8","replace") if n is not None else ""
def field(n,k):
    return n.child_by_field_name(k)
def argtypes(n):
    pars=field(n,"parameters")
    out=[]
    for p in (pars.named_children if pars else []):
        if p.type not in {"formal_parameter","spread_parameter","receiver_parameter"}:continue
        if p.type=="receiver_parameter":continue
        typ=field(p,"type")
        if typ is None:
            typ=next((x for x in p.named_children if x.type not in ("modifiers","variable_declarator","identifier")),None)
        value=text(typ)+text(field(p,"dimensions"))+("[]" if p.type=="spread_parameter" else "")
        out.append(simple_type(value))
    return out
def tokens(n):
    if n.type in SKIP:return
    if not n.child_count or n.type in {"string_literal","character_literal","text_block"}:
        yield text(n);return
    for c in n.children:yield from tokens(c)
def calls(n):
    if n.type in OWNERS|METHOD|{"class_body","interface_body","enum_body"}:return
    if n.type=="method_invocation":
        p=field(n,"arguments")
        yield (text(field(n,"name")),sum(a.type not in SKIP for a in p.named_children) if p else 0)
    for c in n.named_children:yield from calls(c)
@lru_cache(maxsize=200000)
def gram(t):
    return int.from_bytes(hashlib.blake2b("\0".join(t).encode(),digest_size=8,person=b"R9JAVA").digest(),"big")
def features(b):
    if b is None:return set(),set()
    ts=[]
    for c in b.children:
        if c.type not in ("{","}"):ts.extend(tokens(c))
    grams = ({gram(tuple(ts))} if 0<len(ts)<5 else {gram(tuple(ts[k:k+5])) for k in range(len(ts)-4)})
    return grams,set(calls(b))
@lru_cache(maxsize=256)
def parse_cached(cachekey,sha256):
    raw=(CACHE/cachekey).read_bytes();assert sha(raw)==sha256
    tree=PARSER.parse(raw)
    root=tree.root_node
    package=""
    for n in root.named_children:
        if n.type=="package_declaration":
            name=next((c for c in n.named_children if c.type in ("identifier","scoped_identifier")),None)
            package=text(name)
    out=[]
    def visit(n,scope):
        if n.type in OWNERS:
            nm=text(field(n,"name"))
            if not nm:return
            scope=(*scope,nm)
        if n.type=="object_creation_expression":
            # No stable qualified name for anonymous-class members.
            return
        if n.type in METHOD:
            if scope and not n.has_error:
                grams,inv=features(field(n,"body"))
                owner=".".join((package,*scope)).strip(".")
                name=text(field(n,"name"))
                out.append(dict(owner=owner,name=name,types=tuple(argtypes(n)),start=n.start_point.row+1,
                                end=n.end_point.row+1,grams=grams,calls=inv))
            return
        for c in n.named_children:visit(c,scope)
    visit(root,())
    return out,root.has_error
def methodkey(f):return (f["owner"],f["name"],tuple(f["types"]))
def address(f):return [f["path"],f["owner"],f["name"],list(f["types"]),f["start"],f["end"]]
def locate(ms,s):
    owner,name,types=s
    a=[i for i,f in enumerate(ms) if f["owner"]==owner and f["name"]==name and len(f["types"])==len(types)]
    if len(a)>1:return [i for i in a if list(ms[i]["types"])==types]
    return a
def project(record,ids):
    old=[];new=[];parsed=0;bad=0;nbytes=0
    for idx in ids:
        info=record["files"][str(idx)]
        for side,dest in (("old",old),("new",new)):
            if not info[side]:continue
            blob=info[side+"_blob"]
            if "error" in blob:return None
            methods,err=parse_cached(blob["cache"],blob["sha256"])
            bad+=int(err);parsed+=1;nbytes+=blob["size"]
            dest.extend(dict(m,path=info[side],file_id=idx) for m in methods)
    return old,new,dict(blobs=parsed,parse_error_blobs=bad,bytes_input=nbytes)

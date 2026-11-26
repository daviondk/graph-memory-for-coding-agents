"""Resolve conservative module-scope evidence from pre-edit file chunks; never execute source."""
from dataclasses import dataclass
from pathlib import PurePosixPath
import re,posixpath
WORD=re.compile(r"[A-Za-z_$][A-Za-z_0-9$]*")
KEYS=set("""as for while try break continue return pass self cls this that arg args kwargs public private protected void static class def fn func function var const let import from int bool str map list dict null None true false True False new else if elif switch case default impl type trait enum struct interface package mod use super crate mut final extends throws error Error errorf err Println string stringer len any all print println in is or and not assert await async with match raise matchResult""".split())
def words(s):return {v for v in WORD.findall(s) if len(v)>=3 and v not in KEYS}
def ident(s):
    v=WORD.findall(s)
    return v[-1] if v else ""
def changed_names(diff):
    ids=set();declared=set();positions=set();n=0
    for line in diff.splitlines():
        m=re.match(r"^@@ -(\d+)(?:,\d+)? \+\d+",line)
        if m:n=int(m[1]);continue
        if line.startswith(("+++","---","diff --git","index ")):continue
        if line.startswith((" ","-","+")):
            if line[0] in "+-":
                s=line[1:]; # Remove explicit path-like constructs; never treat a target pathname as a symbol clue.
                s=re.sub(r"(?:[.\w-]+[\\/])+(?:[.\w-]+)"," ",s)
                ids|=words(s);positions.add(n)
                for pat in (r"\b(?:def|class|fn|struct|enum|trait|interface|type|function|const|var)\s+([A-Za-z_]\w*)",
                            r"\bfunc\s+(?:\([^)\n]+\)\s*)?([A-Za-z_]\w*)"):
                    declared.update(w for w in re.findall(pat,s) if w in words(w))
            if line[0] in " -":n+=1
    return ids,declared,positions
def cleanmodule(path):
    a=path.split("/")
    if "src" in a:a=a[a.index("src")+1:]
    name=a[-1].rsplit(".",1)[0]
    return ".".join([*a[:-1],*([] if name in ("__init__","index","mod","lib","main") else [name])])
@dataclass
class Scope:
    path:str
    ext:str
    folder:str
    package:str
    module:str
    imports:set
def parse(path,source,repo):
    folder=posixpath.dirname(path);ext=PurePosixPath(path).suffix
    package="";imports=set();module=cleanmodule(path)
    if ext==".go":
        m=re.search(r"(?m)^\s*package\s+([A-Za-z_]\w*)",source);package=m[1] if m else ""
        chunks=re.findall(r"(?ms)^\s*import\s*\((.*?)^\s*\)",source)
        chunks+=re.findall(r"(?m)^\s*import\s+(?:[\w.]+\s+)?(\"[^\"\n]+\")",source)
        for v in chunks:imports.update(re.findall('"([^"\\n]+)"',v))
    elif ext==".java":
        m=re.search(r"(?m)^\s*package\s+([\w.]+)\s*;",source)
        package=m[1] if m else "";module=package+"."+PurePosixPath(path).stem
        imports.update(re.findall(r"(?m)^\s*import\s+(?:static\s+)?([\w.*]+)\s*;",source))
    elif ext==".py":
        pkg=module if path.endswith("__init__.py") else module.rpartition(".")[0]
        for rel,names in re.findall(r"(?m)^[ \t]*from[ \t]+([.\w]+)[ \t]+import[ \t]+([^\n]+)",source):
            dots=len(rel)-len(rel.lstrip("."));base=pkg.split(".") if pkg else []
            if dots>0:base=base[:max(0,len(base)-dots+1)]
            else:base=[]
            absolute=".".join(v for v in base+[rel.lstrip(".")] if v);imports.add(absolute)
            for n in re.findall(r"(?:^|[,(\s]+)([A-Za-z_]\w*)",names):
                imports.add((absolute+"."+n).strip("."))
        for row in re.findall(r"(?m)^[ \t]*import[ \t]+([^\n]+)",source):
            for block in row.split(","):
                m=re.match(r"\s*([\w.]+)",block)
                if m:imports.add(m[1])
    elif ext in (".ts",".tsx",".js",".jsx",".mjs",".cjs"):
        for rel in re.findall(r"""(?:from\s*|require\s*\(\s*|import\s*\(\s*|import\s*)["'](\.[^"']*)["']""",source):
            p=posixpath.normpath(posixpath.join(folder,rel))
            imports.add(re.sub(r"\.(?:tsx?|jsx?|mjs|cjs)$","",p).removesuffix("/index"))
    elif ext==".rs":
        for part in re.findall(r"(?m)^[ \t]*(?:pub(?:\([^)]*\))?\s+)?use\s+([^;\n]+)",source):
            m=re.match(r"(crate|self|super)::((?:[A-Za-z_]\w*::)*[A-Za-z_]\w*)",part)
            if m:
                base=module.rpartition(".")[0].split(".") if m[1]=="super" else module.split(".") if m[1]=="self" else []
                imports.add(".".join(z for z in base+m[2].split("::") if z))
        for sub in re.findall(r"(?m)^[ \t]*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;",source):
            imports.add((module+"."+sub).strip("."))
    return Scope(path,ext,folder,package,module,imports)
def connected(src,dst,repo):
    if src.ext==dst.ext==".go":
        if src.folder==dst.folder and src.package and src.package==dst.package:return "declared_package"
        suffix=(repo+"/"+dst.folder).strip("/")
        for ref in src.imports:
            if ref==suffix or ref.endswith("/"+suffix) or (dst.folder and ref.endswith("/"+dst.folder)):
                return "explicit"
    elif src.ext==dst.ext==".java":
        if src.package and src.package==dst.package:return "declared_package"
        if dst.module in src.imports or dst.package+".*" in src.imports or any(x.startswith(dst.module+".") for x in src.imports):return "explicit"
    elif src.ext==dst.ext==".py":
        if dst.module and dst.module in src.imports:return "explicit"
    elif src.ext in (".ts",".tsx",".js",".jsx",".mjs",".cjs") and dst.ext in (".ts",".tsx",".js",".jsx",".mjs",".cjs"):
        target=re.sub(r"\.(?:tsx?|jsx?|mjs|cjs)$","",dst.path).removesuffix("/index")
        if target in src.imports:return "explicit"
    elif src.ext==dst.ext==".rs":
        if dst.module and any(x==dst.module or x.startswith(dst.module+".") for x in src.imports):return "explicit"
        if src.folder==dst.folder:return "sibling_directory"
    return ""


"""Select 8 files without gold. Reach import neighbors only through six opened seeds."""
import ast
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import tarfile

D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
import predict as reader
from predict import terms
ARMS=("old","init","rare","import")

def discover(issue,files):
    q=terms(issue);focus=reader.focal(issue)
    explicit={p.replace("\\","/") for p in re.findall(r"sphinx[/\\][A-Za-z_0-9/\\]+\.py",issue)}
    table={}
    docs=Counter()
    for path,s in files.items():
        defs={x.lower() for x in re.findall(r"(?m)^\s*(?:def|class)\s+(\w+)",s)}
        if Path(path).name=="__init__.py" and not defs: continue
        stem=terms(Path(path).stem);loc=terms(path)
        fields=(defs&focus,defs&q,stem&q,loc&q)
        table[path]=(path in explicit,fields);docs.update(set().union(*fields))
    idf={t:math.log1p((len(table)+.5)/(n+.5)) for t,n in docs.items()}
    def score(path,rare):
        flag,fields=table[path]
        return 10*int(flag)+sum(w*sum(idf[t] if rare else 1. for t in sorted(v)) for w,v in zip((2.8,1.3,2.,.6),fields))
    def order(allow,rare):
        ranked=[(-score(p,rare),p) for p in table if allow or Path(p).name!="__init__.py"]
        return [p for s,p in sorted(ranked) if s<0]
    first=order(False,False)[:8];expanded=order(True,False)[:8];weighted=order(True,True)
    seed=weighted[:6]
    bonus={}
    for rank,p in enumerate(seed,1):
        try:tree=ast.parse(files[p])
        except (ValueError,SyntaxError):continue
        module=p.removesuffix(".py").replace("/",".")
        package=module.rpartition(".")[0]
        def walk(body):
            for node in body:
                if isinstance(node,(ast.Import,ast.ImportFrom)):yield node
                elif isinstance(node,(ast.If,ast.Try)):
                    yield from walk(node.body)
                    yield from walk(node.orelse)
                    if isinstance(node,ast.Try):
                        yield from walk(node.finalbody)
                        for handler in node.handlers:yield from walk(handler.body)
        for node in walk(tree.body):
            if isinstance(node,ast.ImportFrom):
                try:
                    mod=importlib.util.resolve_name("."*node.level+(node.module or ""),package) if node.level else node.module
                except (ValueError,ImportError):continue
            else:mod=None
            for name in node.names:
                candidates=([mod, (mod+"."+name.name) if mod else name.name] if isinstance(node,ast.ImportFrom) else [name.name])
                for c in candidates:
                    if not c or not (c=="sphinx" or c.startswith("sphinx.")):continue
                    anchor=terms(" ".join([name.name,name.asname or "",c.split(".")[-1]]))
                    if not q&anchor:continue
                    for fp in [c.replace(".","/")+".py",c.replace(".","/")+"/__init__.py"]:
                        if fp not in table or fp in seed:continue
                        val=1/(10+rank)
                        bonus[fp]=max(bonus.get(fp,0),val)
    ranks={p:1/(10+r) for r,p in enumerate(weighted,1)}
    rest=sorted((set(weighted)|set(bonus))-set(seed),key=lambda p:(-(ranks.get(p,0.)+bonus.get(p,0.)),p))
    return {"old":first,"init":expanded,"rare":weighted[:8],"import":seed+rest[:8-len(seed)]},bonus

def one(task):
    f=D/"inputs"/task
    public=reader.read(f/"public.json")
    issue=reader.encoder().decode(reader.ids(public["issue"])[:850])
    files={}
    with tarfile.open(f/"base.tar.gz") as tar:
        for m in tar:
            path=m.name.partition("/")[2];parts=path.split("/")
            if m.isfile() and path.startswith("sphinx/") and path.endswith(".py") and not parts[-1].startswith("test_") and not {"tests","testing","benchmarks"}&set(parts):
                files[path]=tar.extractfile(m).read().decode("utf8",errors="replace")
    paths,neighbors=discover(issue,files)
    cache={};out={}
    for arm in ARMS:
        listing=tuple(paths[arm])
        if listing not in cache:
            blocks,owners=reader.parse({p:files[p] for p in listing})
            scores=reader.bm25([b["meta"]+"\n"+b["text"] for b in blocks],terms(issue))
            spans,packet=reader.pack(blocks,scores)
            cache[listing]={"paths":list(listing),"available":[[b["p"],b["st"],b["en"]] for b in blocks],"kept":spans,"packet":packet,"tokens":len(reader.ids(packet))}
        out[arm]=cache[listing]
    rec={"id":task,"issue":issue,"base":public["rev"],"arms":out,"n_census_files":len(files),"nominated_imports":neighbors}
    dest=D/"predictions"/(task+".json.gz")
    dest.write_bytes(gzip.compress(json.dumps(rec,sort_keys=True,ensure_ascii=False).encode(),mtime=0))
    return task,reader.sha(dest.read_bytes())

def main():
    (D/"predictions").mkdir(exist_ok=True)
    cohort=reader.read(D/"cohort_sphinx.json")["ids"]
    assert len(cohort)==20 and set(cohort).isdisjoint(reader.read(D.parent/"cohort_sphinx.json")["ids"])
    with ProcessPoolExecutor(5) as ex:
        hs={}
        for task,h in ex.map(one,cohort):
            hs[task]=h;print(task,h[:12],flush=True)
    lock={"predictions":hs,"protocol":reader.sha((D/"PROTOCOL_RU.md").read_bytes()),"selection_code":reader.sha(Path(__file__).read_bytes()),"reader_code":reader.sha((D.parent/"predict.py").read_bytes())}
    (D/"predictions.lock.json").write_text(json.dumps(lock,indent=2),"utf8")
if __name__=="__main__":main()

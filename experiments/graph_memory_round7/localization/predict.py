"""Public issue and base source only. Gold and prior scores deliberately live outside this module."""
import ast
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import tarfile
import warnings

os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
from tokenizers import Tokenizer

D=Path(__file__).resolve().parent
WORK=D.parents[1]
OLD=WORK/"graph_memory_round6/repair/transfer"
CODEC=WORK/"memory_session5/live/tokenizer.json"
STOP=set("self cls class def from import true false none this that with have should would which error file line python sympy function return print the and for not but can are when use has will what how does was like then see code one into example following than using gives from about also same expected method".split())
IDENT=re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
SPLIT=re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+")
warnings.filterwarnings("ignore",category=SyntaxWarning)

def sha(x):
    return hashlib.sha256(x).hexdigest()

def read(p):
    return json.loads(p.read_bytes())

@lru_cache(maxsize=1)
def encoder():
    return Tokenizer.from_file(str(CODEC))

def ids(s):
    return encoder().encode(s,add_special_tokens=False).ids

def tokens(s):
    return [x.lower() for w in IDENT.findall(s) for x in dict.fromkeys([w,*SPLIT.findall(w)]) if len(x)>=3 and x.lower() not in STOP]

def terms(s):
    return set(tokens(s))

def focal(issue):
    return terms(" ".join(re.findall(r"\b([A-Za-z_]\w*)\s*\(|\bnevermatch",issue))+" "+" ".join(re.findall(r"\x60([A-Za-z_.]\w*)\x60",issue)))

def sphinx_inputs(task):
    folder=D/"inputs"/task
    data=read(folder/"public.json"); issue=encoder().decode(ids(data["issue"])[:850])
    q=terms(issue); focus=focal(issue)
    explicit={p.replace("\\","/") for p in re.findall(r"sphinx[/\\][A-Za-z_0-9/\\]+\.py",issue)}
    with tarfile.open(folder/"base.tar.gz") as tar:
        files={}
        ranked=[]
        for rec in tar:
            path=rec.name.partition("/")[2]
            parts=path.split("/")
            if not rec.isfile() or not path.startswith("sphinx/") or not path.endswith(".py") or parts[-1].startswith("test_") or parts[-1]=="__init__.py" or any(t in {"tests","testing","benchmarks"} for t in parts):
                continue
            s=tar.extractfile(rec).read().decode("utf8",errors="replace")
            defs={x.lower() for x in re.findall(r"(?m)^\s*(?:def|class)\s+(\w+)",s)}
            matches=defs&q
            score=10*int(path in explicit)+2.8*len(matches&focus)+1.3*len(matches)+2*len(q&terms(Path(path).stem))+.6*len(q&terms(path))
            if score>0:
                files[path]=s;ranked.append((-score,path))
        paths=[p for score,p in sorted(ranked)[:8]]
    return issue,paths,{p:files[p] for p in paths},None,data["rev"]

def inputs(task):
    if task.startswith("sphinx"):
        return sphinx_inputs(task)
    td=OLD/"tasks"/task
    public=read(td/"public.json")
    packet=json.loads(gzip.decompress((td/"packets.json.gz").read_bytes()))
    issue=encoder().decode(ids(public["problem_statement"])[:850])
    assert issue==packet["issue"]
    paths=packet["paths"]
    files={p:(td/"base"/p).read_text("utf8",errors="replace") for p in paths}
    flat=(packet["kept"]["flat"],packet["packets"]["flat"])
    return issue,paths,files,flat,public["base_commit"]

def parse(files):
    blocks=[];owners=[]
    for p,src in files.items():
        lines=src.splitlines()
        try:
            tree=ast.parse("\n".join(lines))
        except (SyntaxError,ValueError):
            continue
        def walk(body,cl=""):
            for node in body:
                if isinstance(node,ast.ClassDef):
                    walk(node.body,node.name)
                if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    continue
                first=node.body[0]; doc=ast.get_docstring(node,clean=False) or ""
                lo=first.lineno if doc else 0
                hi=first.end_lineno if doc else 0
                j=len(owners)
                meta=f"{p} {cl} {node.name}"
                owners.append((p,meta,cl,node.name,doc))
                for st in range(node.lineno,node.end_lineno+1,14):
                    en=min(st+13,node.end_lineno)
                    text="\n".join(lines[st-1:en])
                    blocks.append({"p":p,"st":st,"en":en,"j":j,"text":text,"owner":f"{cl}.{node.name}","meta":meta,
                                   "executable":any(k>hi for k in range(st,en+1))})
        walk(tree.body)
    return blocks,owners

def bm25(corpus,query):
    cs=[Counter(tokens(s)) for s in corpus]
    n=len(cs); df=Counter()
    for bag in cs:
        df.update(bag.keys())
    mean=sum(b.total() for b in cs)/max(n,1)
    if not mean:return [0.]*n
    out=[]
    for b in cs:
        score=0.
        for t in sorted(query.intersection(b)):
            f=b[t];idf=math.log1p((n-df[t]+.5)/(df[t]+.5))
            score+=idf*(2.2*f)/(f+1.2*(.25+.75*b.total()/mean))
        out.append(score)
    return out

def dense_position(scores):
    first={}
    for i,s in enumerate(sorted(scores,reverse=True),1):
        first.setdefault(s,i)
    return [1/(30+first[s]) if s>0 else 0. for s in scores]

def relation_scores(owners,issue,shuffle,task):
    q=terms(issue)
    documents=[f"{cl} {fn}\n{doc}" if doc else "" for p,meta,cl,fn,doc in owners]
    scores=dense_position(bm25(documents,q))
    if shuffle:
        rng=random.Random(task+"|r7-doc-binding")
        for p in sorted({o[0] for o in owners}):
            indices=[i for i,o in enumerate(owners) if o[0]==p]
            values=[scores[i] for i in indices]
            rng.shuffle(values)
            for i,v in zip(indices,values):
                scores[i]=v
    return scores

def previous_flat(blocks,owners,issue):
    q=terms(issue);focus=focal(issue)
    cover=[terms(b["text"]) for b in blocks];df=Counter()
    for t in cover:df.update(t)
    def weight(v):
        return sum(math.log1p((len(blocks)+1)/(df[t]+1)) for t in sorted(v))
    scores=[]
    for b,v in zip(blocks,cover):
        p,_,cl,fn,_=owners[b["j"]];name=terms(fn+" "+cl);common=q&v
        score=weight(common)/math.sqrt(max(7,len(v)))+.90*weight(name&q)+.8*weight(name&focus)+.4*weight(terms(p)&q)+.25*weight(common&focus)
        scores.append(score)
    return scores

def pack(blocks,scores):
    order=sorted(range(len(blocks)),key=lambda i:(-scores[i],blocks[i]["p"],blocks[i]["st"]))
    chosen=[];records=[];used=0
    for idx in order:
        b=blocks[idx]
        record=f"{b['p']}  L{b['st']}-{b['en']}  {b['owner']}\n{b['text']}"
        size=len(ids(record))+2
        if size+used>1800:continue
        chosen.append([b["p"],b["st"],b["en"]]);records.append(record);used+=size
        if used>1770:break
    content="\n\n".join(records)
    while len(ids(content))>1800:
        chosen.pop();records.pop();content="\n\n".join(records)
    return chosen,content

def one(task):
    issue,paths,files,flat_prior,rev=inputs(task)
    blocks,owners=parse(files);q=terms(issue)
    base=bm25([b["meta"]+"\n"+b["text"] for b in blocks],q)
    ranked=dense_position(base)
    params={}
    for arm,shuf in [("doclink",False),("shuffled",True)]:
        s=relation_scores(owners,issue,shuf,task)
        params[arm]=[v+(s[b["j"]] if b["executable"] else 0.) for v,b in zip(ranked,blocks)]
    params["bm25"]=base
    if flat_prior is None:params["r6_flat"]=previous_flat(blocks,owners,issue)
    pred={}
    for arm,scores in params.items():
        chosen,packet=pack(blocks,scores)
        pred[arm]={"kept":chosen,"packet":packet,"tokens":len(ids(packet))}
    if flat_prior is not None:
        chosen,packet=flat_prior
        pred["r6_flat"]={"kept":chosen,"packet":packet,"tokens":len(ids(packet))}
    rec={"id":task,"base":rev,"issue":issue,"paths":paths,"file_sha":{p:sha(t.encode()) for p,t in files.items()},
         "available":[[b["p"],b["st"],b["en"]] for b in blocks],"arms":pred}
    raw=json.dumps(rec,ensure_ascii=False,sort_keys=True).encode()
    output=D/"predictions"/(task+".json.gz");output.write_bytes(gzip.compress(raw,mtime=0))
    return task,sha(output.read_bytes())

def main():
    (D/"predictions").mkdir(exist_ok=True)
    sym=read(OLD/"cohort.json")["ids"]
    other=read(D/"cohort_sphinx.json")["ids"]
    assert len(set(sym+other))==len(sym)+len(other)
    with ProcessPoolExecutor(5) as pool:
        hashes={}
        for task,h in pool.map(one,sym+other):
            hashes[task]=h
            print(task,h[:12],flush=True)
    lock={"protocol":sha((D/"PROTOCOL_RU.md").read_bytes()),"code":sha(Path(__file__).read_bytes()),"tokenizer":sha(CODEC.read_bytes()),"predictions":hashes}
    (D/"predictions.lock.json").write_text(json.dumps(lock,indent=2),"utf8")
if __name__=="__main__":
    main()

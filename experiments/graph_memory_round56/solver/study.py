"""Project, data and text utility functions. Head commits are pinned before generating any answer."""
import ast
from collections import Counter
import doctest
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
RAW=Path("D:/CodexResearch/x20-r56-solver")
R52=HERE.parents[1]/"graph_memory_round52"
SPECS={
    "mahmoud/boltons":("d31d821d56c8f7756af9c30a864077f2e5855321","boltons",
                       "iterutils strutils mathutils statsutils listutils setutils dictutils timeutils"),
    "more-itertools/more-itertools":("aa9977698a5e6ae15d3fdfac08a5fc5621c4e179","more_itertools",
                                      "more recipes"),
    "pytoolz/toolz":("451af60dec590a6010e2babdbf391ea8f815122f","toolz",
                     "itertoolz functoolz dicttoolz recipes"),
}
ARMS=("file8","file_all","global32","full_bm25","contract")
IMAGE="sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30"
RISK=re.compile(r"\b(?:attack|exploit|malware|payload|bypass|vulnerability|credential|security|passwd|password|token_urlsafe|secret|encrypt|decrypt|ssl|socket|http|https|network|subprocess|filesystem|symlink|unlink|exec|eval|open|fork|thread|pickle|signal|environ|stdout|stderr|filename|fileno|read_file|socketserver|ctypes|breakpoint|__subclasses__|__globals__)\b",re.I)
FORBID_TARGET=re.compile(r"(secure|password|shell|exec|file|path|uuid|random|timeit|date.today|datetime.now|sleep\(|perf_counter|stdout|stderr|socket|crypt|process|resource|metaclass|environ)",re.I)
def digest(b):
    return sha256(b).hexdigest()
def write(n,obj):
    p=HERE/n
    b=(json.dumps(obj,ensure_ascii=True,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def read(n):
    p=HERE/n
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def git(repo,*args,input=None):
    return subprocess.check_output(["git","-C",str(RAW/repo.replace("/","__")),*args],input=input)
def terms(s):
    raw=re.findall(r"[A-Za-z][A-Za-z_0-9]*",s.lower())
    return [part for w in raw for part in dict.fromkeys((w,*w.split("_"))) if len(part)>1]
def score_query(episodes,task):
    # Corpus statistics stay fixed across arms; only candidate availability changes.
    tokens=[terms(e["address"]+" "+e["text"]) for e in episodes]
    freq=Counter(w for doc in tokens for w in set(doc))
    query=terms((task["name"]+" ")*3+task["question"])
    n=len(tokens);avg=sum(map(len,tokens))/n
    def bm25(doc):
        counts=Counter(doc)
        return sum(math.log1p((n-freq[w]+.5)/(freq[w]+.5))*c*2.2/(c+1.2*(.25+.75*len(doc)/avg))
                   for w in query if (c:=counts.get(w,0)))
    return [bm25(doc) for doc in tokens]
def target_modules(repo):
    _,pkg,mods=SPECS[repo]
    return {f"{pkg}/{m}.py" for m in mods.split()}

def target_examples(doc,symbol):
    try:ex=doctest.DocTestParser().get_examples(doc)
    except ValueError:return None
    if sum(bool(e.want.strip()) for e in ex)<2 or not any(re.search(r"\b"+symbol+r"\s*\(",e.source) for e in ex):
        return None
    if any(RISK.search(e.source) or FORBID_TARGET.search(e.source) or doctest.SKIP in e.options for e in ex):
        return None
    return ex

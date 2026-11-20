"""Pinned data source and input-only utilities, no project execution."""
from pathlib import Path
import gzip
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parent
CACHE=Path("D:/CodexResearch/x20-round9-java-oracle")
ORACLE_REV="136ee7da5a3a13e10bea2ca8f4f8342f3fd40c98"
ORACLE=f"https://raw.githubusercontent.com/tsantalis/RefactoringMiner/{ORACLE_REV}/src/test/resources/oracle/data.json"
PROJECTS=["checkstyle/checkstyle","google/guava","google/closure-compiler","apache/drill",
          "graphhopper/graphhopper","antlr/antlr4","gradle/gradle","real-logic/Aeron",
          "processing/processing","puniverse/quasar","neo4j/neo4j"]
QUOTAS={"Inline Method":4,"Rename Method":2,"Move Method":2}
UNSAFE=re.compile(r"exploit|vulnerab|malware|ransom|security|crypto|password|credential|authentication|authorization|overflow attack|(?:^|[/_\s-])CVE|(?:command|sql|exception)injection|(?:command|SQL) injection|denial.of.service",re.I)
def sha(b):return hashlib.sha256(b).hexdigest()
def pack(x):return json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(",",":")).encode()
def read(name):
    p=ROOT/name
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(name,x):
    p=ROOT/name
    data=gzip.compress(pack(x),mtime=0) if p.suffix==".gz" else (json.dumps(x,indent=2,ensure_ascii=False,sort_keys=True)+"\n").encode()
    p.write_bytes(data)
def hashfiles(names):return {n:sha((ROOT/n).read_bytes()) for n in names}
def check(hashmap):
    assert all(sha((ROOT/n).read_bytes())==v for n,v in hashmap.items())
def split_params(s):
    if not s.strip():return []
    out=[];start=depth=0
    for i,c in enumerate(s):
        if c in "<[(":depth+=1
        elif c in ">])":depth-=1
        elif c=="," and depth==0:
            out.append(s[start:i].strip());start=i+1
    out.append(s[start:].strip())
    return out
def simple_type(s):
    return re.sub(r"\s+","",re.sub(r"\b(?:[a-z_][\w$]*\.)+(?=[A-Z_])","",s)).replace("...","[]")
def desc_signature(text,owner):
    m=re.fullmatch(r"(?:public|private|protected|package)\s+([\w$]+)\((.*?)\)(?:\s*:\s*.*)?",text)
    if not m:return None
    args=split_params(m[2])
    if any(" " not in x for x in args):return None
    return [owner,m[1],[simple_type(x.split(" ",1)[1]) for x in args]]
def endpoints(t,desc):
    if t=="Move Method":
        m=re.fullmatch(r"Move Method (.+?) from class (\S+) to (.+?) from class (\S+)",desc)
        if m:return desc_signature(m[1],m[2]),desc_signature(m[3],m[4])
    else:
        word="inlined" if t=="Inline Method" else "renamed"
        m=re.fullmatch(re.escape(t)+r" (.+?) "+word+r" to (.+?) in class (\S+)",desc)
        if m:return desc_signature(m[1],m[3]),desc_signature(m[2],m[3])
    return None,None

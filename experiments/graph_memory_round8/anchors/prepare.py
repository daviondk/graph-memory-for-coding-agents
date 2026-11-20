"""Acquire the public annotation file and read Git source without importing project code."""
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent
CACHE=Path("D:/CodexResearch/x20-round8-oracle-cache")
REV="136ee7da5a3a13e10bea2ca8f4f8342f3fd40c98"
ORACLE=f"https://raw.githubusercontent.com/tsantalis/RefactoringMiner/{REV}/src/test/resources/oracle/python-dataset/data.json"
PROJECTS=["dit/dit","asyml/texar","kkroening/ffmpeg-python"]
TYPES=("Rename Method","Move Method","Move And Rename Method")
def hashbytes(b):return hashlib.sha256(b).hexdigest()
def save(name,obj):
    (ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
def load(name):return json.loads((ROOT/name).read_bytes())
def repo(project):return CACHE/(project.split("/")[-1]+".git")
def git(project,*args):
    return subprocess.check_output(["git","--git-dir",str(repo(project)),*args])
def parse_label(ref):
    decl=r"(?:public|private|protected|package)\s+([\w$]+)\(.*?\)"
    if ref["type"]=="Rename Method":
        m=re.fullmatch(r"Rename Method "+decl+r"\s+renamed to\s+"+decl+r"\s+in class\s+(\S+)",ref["description"])
        if m:return m[1],m[3],m[2],m[3]
    else:
        m=re.fullmatch(re.escape(ref["type"])+" "+decl+r"\s+from class\s+(\S+)\s+to\s+"+decl+r"\s+from class\s+(\S+)",ref["description"])
        if m:return tuple(m.groups())
    return None
def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    path=CACHE/"python-data.json"
    if not path.is_file():path.write_bytes(urlopen(ORACLE,timeout=45).read())
    for project in PROJECTS:
        if not repo(project).exists():subprocess.run(["git","clone","--bare","--quiet","https://github.com/"+project+".git",str(repo(project))],check=True)
    ro=[];gold={};excluded=Counter();seen=set()
    safe=re.compile(r"exploit|malware|ransom|vulnerability|penetration|cve-|secret_key_agreement",re.I)
    for row in json.loads(path.read_bytes()):
        project=row["repository"].removeprefix("https://github.com/").removesuffix(".git")
        assert project in PROJECTS
        sha=row["sha1"]
        tags=[ref for ref in row["refactorings"] if ref["type"] in TYPES and ref.get("validation")=="TP"]
        if not tags:continue
        parents=git(project,"rev-list","--parents","-n","1",sha).decode().split()[1:]
        if len(parents)!=1:
            excluded["merge_or_root"]+=len(tags);continue
        for ref in tags:
            if safe.search(ref["description"]):
                excluded["out_of_scope"]+=1;continue
            pair=parse_label(ref)
            if not pair:
                excluded["unparsed_annotation"]+=1;continue
            key=(project,sha,ref["type"],*pair)
            if key in seen:
                excluded["duplicate"]+=1;continue
            seen.add(key)
            case=hashbytes("|".join(key).encode())[:18]
            ro.append(dict(case=case,project=project,old=parents[0],new=sha,name=pair[0],scope=pair[1]))
            gold[case]=dict(name=pair[2],scope=pair[3],kind=ref["type"])
    save("queries.json",ro);save("labels.json",gold)
    save("source-lock.json",dict(oracle=ORACLE,oracle_sha256=hashbytes(path.read_bytes()),ref=REV,projects=PROJECTS,
        kept=len(ro),excluded=dict(excluded),hashes={n:hashbytes((ROOT/n).read_bytes()) for n in ("PROTOCOL.md","queries.json","labels.json")}))
    print("Queries before source resolution",len(ro),dict(excluded))
if __name__=="__main__":main()

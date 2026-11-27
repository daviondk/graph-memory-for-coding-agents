"""Define the cohort without reading relation labels, target patches or search results."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
STAGE=Path("D:/CodexResearch/x20-swe-context")
OLD=Path("D:/CodexResearch/x20-bench-workspace/work/sota_round/swe_context")
REPOS={"sympy/sympy","matplotlib/matplotlib","scikit-learn/scikit-learn","astropy/astropy","mwaskom/seaborn",
       "pydata/xarray","pytest-dev/pytest","sphinx-doc/sphinx"}
RISK=re.compile(r"\b(?:vulnerab\w*|exploit\w*|malware|attack\w*|security|cve|injection|credentials?|bioweapon|weapons?|biohazard|pathogen\w*|biolog\w*|genomic\w*|virus|attackers?|ransomware|bypass|cytotox\w*)\b",re.I)

def get(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)

def put(n,obj):
    p=HERE/n;b=(json.dumps(obj,sort_keys=True,ensure_ascii=True,indent=2 if p.suffix!=".gz" else None)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def safe_text(t):
    return not RISK.search(t)

def main():
    import pyarrow.parquet as pq
    qtext=get(OLD/"queries.json")
    row=pq.read_table(STAGE/"SWEContextBench_Related_Lite.parquet",columns=["repo","instance_id","problem_statement"]).to_pylist()
    eligible={}
    for i,r in enumerate(row):
        if r["repo"] in REPOS and safe_text(r["problem_statement"]):
            assert qtext[i]["group"]=="lite" and qtext[i]["ordinal"]==i
            eligible[str(i)]={"id":r["instance_id"],"repo":r["repo"],"query":qtext[i]["query"]}
    lib=list(csv.DictReader((OLD/"evaluation_library.csv").open(encoding="utf8")))
    cards={x["key"]:x for x in get(OLD/"cards.json")}
    def repo(s):
        return s.rsplit("-",1)[0].replace("__","/")
    ok=[]
    for r in lib:
        k=r["trace_key"]
        if repo(r["instance_id"]) in REPOS and safe_text(cards[k]["symptom"]+" "+cards[k]["closure"]):
            ok.append(k)
    put("cohort.json.gz",dict(tasks=eligible,trace_keys=sorted(ok)))
    print(len(eligible),len(ok))
    for i,v in eligible.items():
        print(i,v["repo"],v["query"][:90].encode("ascii","replace").decode())

if __name__=="__main__":main()

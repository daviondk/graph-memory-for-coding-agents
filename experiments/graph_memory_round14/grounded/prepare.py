"""Prepare graph-evidence menus using only already displayed observations and issue text."""
import collections
import gzip
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RANK=ROOT.parents[1]/"graph_memory_round13/reformulation"
sys.path.insert(0,str(RANK))
import prefix, rank
from pyarrow import parquet

REPOS=("aws-cloudformation/cfn-lint","getmoto/moto","dbt-labs/dbt-redshift","Scille/umongo","Sinaptik-AI/pandas-ai")
FORBID=re.compile(r"\b(vulnerabilit(?:y|ies)|exploits?|attacks?|hacking|authentication|authorization|privilege|bypass|sqli|injection|CVE-\d+|denial of service|security|credentials?|penetration|intrusion)\b",re.I)

def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,x):
    b=json.dumps(x,sort_keys=True,ensure_ascii=False,indent=1).encode()
    (ROOT/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)
def read(name):
    b=(ROOT/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)

def qualifying(row):
    docs=row["docs"]
    if len(docs)<3:return
    ranks,_=rank.calculate(row)
    target=ranks["graph"][0]
    ids={p:{s.lower() for s in rank.IDENT.findall(d["snip"]) if len(s)>=5 and s.lower() not in rank.STOP} for p,d in docs.items()}
    freq=collections.Counter(t for terms in ids.values() for t in terms)
    query=set(rank.IDENT.findall((row["issue"]+" "+row["key"]["literal"]).lower()))
    options=[((freq[t],-int(t in query),-len(t),p,t),p,t) for p,words in ids.items() if p!=target
             for t in words & ids[target] if 2<=freq[t]<=math.ceil(len(docs)/2)]
    if not options:return
    _,neighbor,symbol=min(options)
    paths=list(dict.fromkeys([target,neighbor,ranks["strong"][0],*sorted(docs,key=lambda p:(-docs[p]["last"],p))]))[:6]
    paths.sort(key=lambda p:sha((row["id"]+p).encode()))
    # Pair order is fixed from the menu and independently of which is the proposed graph target.
    pair=sorted([target,neighbor],key=paths.index)
    return dict(id=row["id"],iid=row["iid"],repo=row["repo"],step=row["index"],issue=row["issue"],search=row["key"],
                menu=[dict(path=p,steps_since_address=row["index"]-docs[p]["last"],visible_excerpt=docs[p]["snip"][:200]) for p in paths],
                target=target,pair=pair,symbol=symbol,df=freq[symbol],n_docs=len(docs))

def main():
    v=prefix.V
    all_files={s["rfilename"]:s for s in prefix.ext.get(v/"memory-stage-fetch/source-manifest.json")["siblings"]}
    safe_bases=parquet.read_table("D:/CodexResearch/x20-round12-negative-objects/SWE-rebench-V2.parquet",columns=["instance_id","base_commit","repo"]).to_pylist()
    bases={r["instance_id"]:r["base_commit"] for r in safe_bases}
    counts=collections.Counter(); roster=[];selected=[]
    for repo in REPOS:
        folder=v/"benchmark/history/python"/repo.replace("/","__")
        for f in sorted(folder.glob("*/*.traj.json")):
            counts["source"]+=1
            b=f.read_bytes();k=f.relative_to(v/"benchmark").as_posix();q=all_files[k]
            expected=q.get("lfs",{}).get("sha256") or q["blobId"]
            actual=sha(b) if len(expected)==64 else hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
            assert expected==actual
            issue=next(m["content"] for m in json.loads(b)["messages"] if m["role"]=="user").partition("</pr_description>")[0]
            if FORBID.search(issue) or prefix.ext.BAD.search(issue):
                counts["excluded_issue"]+=1;continue
            rec={"iid":f.parent.name,"repo":repo,"file":k,"sha":sha(b),"base":bases[f.parent.name]}
            roster.append(rec);choice=None
            for row in prefix.sample(rec):
                counts["empty_anchors"]+=1
                cand=qualifying(row)
                if cand:
                    counts["eligible_anchors"]+=1
                    if choice is None:choice={**cand,"base":rec["base"]}
            if choice:selected.append(choice)
    order=sorted(selected,key=lambda c:sha(("r14-evidence|"+c["iid"]).encode()))
    counts["eligible_tasks"]=len(order)
    save("roster.json",roster);save("cases.gz",order[:30]);save("flow.json",dict(counts=counts,selected=len(order[:30]),by_repo=collections.Counter(c["repo"] for c in order[:30])))
    save("assignment.json",dict(files={k:sha((ROOT/k).read_bytes()) for k in ("PROTOCOL_RU.md","prepare.py","solver.py","cases.gz","roster.json","flow.json")},
          borrowed={k:sha((RANK/k).read_bytes()) for k in ("prefix.py","rank.py")}))
    print(read("flow.json"))
if __name__=="__main__":main()

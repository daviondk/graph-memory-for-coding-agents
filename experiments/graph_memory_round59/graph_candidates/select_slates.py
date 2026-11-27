"""Construct four five-item slates from historical traces and visible issue text."""
from collections import Counter
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
FIRST=HERE.parent/"agent_benchmark"
sys.path.insert(0,str(FIRST))
import graph
import roster
OLD,STAGE,get,sha=roster.OLD,roster.STAGE,roster.get,roster.sha
IDS=[*range(2,8),*range(9,25),28,*range(32,38),52,54,55,58]
TOPICS={"django/django":r"model|form|orm\b|quer(?:y|ies)|database|migration|index|annotat|widget|enum|foreignkey|field|table",
        "pallets/flask":r"blueprint|command|template|display|text|format",
        "psf/requests":r"\bunicode|\bencod|\bdecod|iter_content|\bformat",
        "pylint-dev/pylint":r"check|lint|warning|inference|recursive|class|format|error"}
SENSITIVE=re.compile(r"secur|vulnerab|exploit|csrf|xss|cross.site|sql.injection|authentication|oauth|authoriz|\bpermission|\bsession|\bpassword|\bsandbox|\bshell|\bsymlink|arbitrar|\bmalicious|remote code|template injection|path traversal|cryptograph|\bSSL\b|\bTLS\b|\bcookie|\bpickle",re.I)
STOP=set("python django src lib docs documentation code test tests none true false file class def assert return self from import model models py rst html example common main update method value result added issue error exception warning library repository implementation read edit utils testbed ability".split())


def put(n,z):
    p=HERE/n;b=(json.dumps(z,ensure_ascii=True,sort_keys=True,indent=2 if p.suffix!=".gz" else None)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)


def tokens(s):
    words=set()
    for cluster in re.findall(r"[A-Za-z][A-Za-z0-9_]+",s):
        split=re.sub(r"([A-Z]+)([A-Z][a-z])",r"\1 \2",re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",cluster))
        words.update(t.lower() for t in [cluster,*re.split("[ _]+",split)] if len(t)>=3)
    return words-STOP


def lex(g):
    src=[tokens(p) for p in g["src"]]
    dst=[tokens(p+" "+" ".join(g["hints"][p])) for p in g["dst"]]
    return src,dst,set().union(*src,*dst)


def main():
    import pyarrow.parquet as pq
    rows=pq.read_table(STAGE/"SWEContextBench_Related_Lite.parquet",columns=["instance_id","repo","problem_statement"]).to_pylist()
    oldco=get(FIRST/"cohort.json.gz")
    assert not set(IDS)&set(map(int,oldco["tasks"]))
    assert not {rows[i]["repo"] for i in IDS}&{r["repo"] for r in oldco["tasks"].values()}
    cards={r["key"]:r for r in get(OLD/"cards.json")}
    library={r["trace_key"]:r["instance_id"] for r in csv.DictReader((OLD/"evaluation_library.csv").open(encoding="utf8"))}
    new=[]
    for k,case in library.items():
        repo=case.rsplit("-",1)[0].replace("__","/")
        if repo not in TOPICS:continue
        title=cards[k]["symptom"]; msg=title+" "+cards[k]["closure"]
        if roster.safe_text(msg) and not SENSITIVE.search(msg) and re.search(TOPICS[repo],title,re.I):
            new.append(k)
    reconstructed={k:graph.extract(STAGE/"traces"/(k+".jsonl")) for k in new}
    graphs={**get(FIRST/"graph.json.gz"),**reconstructed}
    expected={r["relative"]:r["sha256"] for r in get(OLD/"source.json")["files"]}
    assert all(sha(STAGE/"traces"/(k+".jsonl"))==expected["traces/"+k+".jsonl"] for k in new)
    put("new-graphs.json.gz",reconstructed)
    bags={k:lex(v) for k,v in graphs.items()}
    df=Counter(w for _,_,terms in bags.values() for w in terms)
    n=len(graphs);weight={w:1+math.log((n+1)/(c+1)) for w,c in df.items() if c<=max(2,n//5)}
    ranks=get(OLD/"blind_ranks.json");questions=get(OLD/"queries.json")
    tasks={};plans={};details={}
    for i in IDS:
        q=str(i);t=rows[i]
        assert t["repo"] in TOPICS and roster.safe_text(t["problem_statement"])
        tasks[q]=dict(repo=t["repo"],id=t["instance_id"],query=questions[i]["query"])
        orig=ranks[i]["fusion"][:5];assert len(set(orig))==5
        qt=tokens(questions[i]["query"]) & weight.keys()
        rankings={arm:{} for arm in ("vertex","true","rotation")}
        for k,(ss,dd,vocab) in bags.items():
            if k in orig[:4]:continue
            hit=qt&vocab
            if len(hit)<2:continue
            base=sum(weight[x] for x in sorted(hit))
            rankings["vertex"][k]=base
            ee=graphs[k]["edges"];endpoints=[b for a,b in ee]
            for arm in ("true","rotation"):
                edges=ee if arm=="true" else [(a,endpoints[(j+1)%len(ee)]) for j,(a,b) in enumerate(ee)]
                extra=max((min(weight[x],weight[y]) for a,b in edges for x in qt&ss[a-1]
                           for y in qt&dd[b-1] if x!=y),default=0)
                rankings[arm][k]=base+extra
        out={"fusion":orig};dec={}
        for arm,scores in rankings.items():
            winner=min(scores,key=lambda k:(-scores[k],k!=orig[4],k)) if scores else orig[4]
            out[arm]=orig[:4]+[winner]
            dec[arm]=dict(selected=winner,score=scores.get(winner),eligible=len(scores),
                          first_ten=[[k,round(scores[k],5)] for k in sorted(scores,key=lambda k:(-scores[k],k!=orig[4],k))[:10]])
        plans[q]=out;details[q]=dec
    put("roster.json.gz",dict(tasks=tasks,earlier_target_ordinals=sorted(map(int,oldco["tasks"])),eligible_source_ids=sorted(graphs)))
    put("slates.json.gz",plans);put("decisions.json.gz",details)
    put("selection-seal.json",dict(protocol=sha(HERE/"PROTOCOL_RU.md"),source=sha(HERE/"select_slates.py"),corpus=sha(FIRST/"graph.json.gz"),
            extractor=sha(FIRST/"graph.py"),original_ranks=sha(OLD/"blind_ranks.json"),hashes={n:sha(HERE/n) for n in
                ("new-graphs.json.gz","roster.json.gz","slates.json.gz","decisions.json.gz")}))
    print("Locked",len(IDS),"tasks in",len({t["repo"] for t in tasks.values()}),"new projects,",
          len(new),"new historical graphs. Graph and flat differing fifth positions",sum(p["true"]!=p["vertex"] for p in plans.values()))


if __name__=="__main__":main()

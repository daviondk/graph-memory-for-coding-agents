"""Blinded replay of reversing verified extractions, with disjoint commit IDs."""
import collections
import json
import re
import sys
from call_edge import flag
from prepare import CACHE, ROOT, git, hashbytes,load,save
from predict import front,locate,predict,tag
from score import confident


def setup():
    used={q["new"] for q in load("queries.json")}|{q["commit"] for q in load("transfer-queries.json")}
    cases=collections.defaultdict(lambda:collections.defaultdict(set))
    stats=collections.Counter()
    for entry in json.loads((CACHE/"python-data.json").read_bytes()):
        project=entry["repository"].removeprefix("https://github.com/").removesuffix(".git")
        sha=entry["sha1"]
        for ref in entry["refactorings"]:
            if ref["type"] not in ("Extract Method","Extract And Move Method") or ref["validation"]!="TP":
                continue
            stats["annotations"]+=1
            if sha in used:
                stats["other_panel_commit"]+=1
                continue
            desc=ref["description"]
            if re.search(r"exploit|malware|ransom|vulnerability|penetration|cve-|secret_key_agreement",desc,re.I):
                stats["out_of_scope"]+=1
                continue
            m=re.fullmatch(re.escape(ref["type"])+r" \w+ ([\w$]+)\(.*?\) extracted from \w+ ([\w$]+)\(.*?\) in class (\S+)(?: & moved to class (\S+))?",desc)
            if not m:
                stats["unparsed_description"]+=1
                continue
            parents=git(project,"rev-list","--parents","-n","1",sha).decode().split()[1:]
            if len(parents)!=1:
                stats["not_single_parent"]+=1
                continue
            helper,caller,caller_scope,helper_scope=m.groups()
            caller_key=(caller,caller_scope)
            source=(project,sha,parents[0])
            cases[(*source,helper,helper_scope or caller_scope)]["helper"].add(caller_key)
            cases[(*source,*caller_key)]["caller"].add(caller_key)
    qs=[];labs={}
    for fields, group in cases.items():
        if len(group)!=1:
            stats["contradictory_source"]+=1
            continue
        project,old,new,name,scope=fields
        cid=hashbytes("|".join(fields).encode())[:18]
        role,targets=next(iter(group.items()))
        qs.append(dict(case=cid,project=project,old=old,new=new,name=name,scope=scope))
        labs[cid]=dict(role=role,targets=sorted(targets))
    save("reverse-queries.json",qs)
    save("reverse-labels.json",labs)
    save("reverse-source.json",dict(flow=stats,queries=len(qs),commits=len({q["old"] for q in qs}),overlap=sorted({q["old"] for q in qs}&used)))


def forecasts():
    groups=collections.defaultdict(list)
    for q in load("reverse-queries.json"):
        groups[q["project"],q["old"],q["new"]].append(q)
    rows=[]
    for (project,old,new),qs in groups.items():
        prev,curr,_=front(project,old,new)
        for q in qs:
            ix=locate(prev,q["name"],q["scope"])
            p=dict(case=q["case"],commit=old,n_old=len(ix))
            rows.append(p)
            if len(ix)!=1:
                continue
            src=prev[ix[0]]
            ranks,scores,_=predict(src,[m for m in prev if m["path"]==src["path"]],curr)
            rank=ranks["mixed"]
            p.update(origin=tag(src),pool=[tag(m) for m in curr],top=rank[0] if rank else None,accept=confident(scores),verified=False,flag=False)
            if not p["accept"]:
                continue
            dst=curr[rank[0]]
            k=(dst["path"],dst["qual"])
            prior=[m for m in prev if (m["path"],m["qual"])==k]
            unchanged=(src["path"],src["qual"])!=k and len(prior)==1 and bool(dst["grams"][0]) and prior[0]["grams"][0]==dst["grams"][0]
            p["verified"]=not unchanged
            p["flag"]=p["verified"] and flag(project,old,new,tag(src),tag(dst))
    save("reverse-predictions.json",rows)
    files=["REVERSAL.md","CALL_EDGE.md","reverse.py","call_edge.py","predict.py","score.py","reverse-queries.json","reverse-predictions.json"]
    save("reverse-lock.json",{f:hashbytes((ROOT/f).read_bytes()) for f in files})


def evaluate():
    for f,h in load("reverse-lock.json").items():
        assert hashbytes((ROOT/f).read_bytes())==h
    labels=load("reverse-labels.json")
    groups=collections.defaultdict(collections.Counter);out=[]
    for r in load("reverse-predictions.json"):
        label=labels[r["case"]]; role=label["role"]; g=groups[role];g["queries"]+=1
        if r["n_old"]!=1:
            g["unresolved_old"]+=1
            continue
        pool=[dict(path=a,qual=b,name=b.split(".")[-1],line=c) for a,b,c in r["pool"]]
        if role=="helper" and any([f["path"],f["qual"]]==r["origin"][:2] for f in pool):
            g["ambiguous_survival"]+=1
            continue
        viable=set()
        for name,scope in label["targets"]:
            matches=locate(pool,name,scope)
            if len(matches)==1:
                viable.add(matches[0])
        top_correct=r["top"] is not None and r["top"] in viable
        accepted=r["verified"]; flagged=r["flag"];after=accepted and not flagged
        g["n"]+=1
        for key,v in dict(target_recognized=bool(viable),rank1_target=top_correct,confidence_only=r["accept"],accepted=accepted,
                flagged=flagged,retained=after,accepted_target=accepted and top_correct,retained_target=after and top_correct,
                flagged_target=flagged and top_correct).items():
            g[key]+=int(v)
        out.append(dict(case=r["case"],commit=r["commit"],role=role,target_resolved=bool(viable),correct_target=top_correct,
                        accepted=accepted,flagged=flagged,retained=after))
    result=dict(n=len(out),commits=len({r["commit"] for r in out}),source=load("reverse-source.json"),groups=groups)
    save("reverse-outcomes.json",out);save("reverse-results.json",result)
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    {"prepare":setup,"predict":forecasts,"score":evaluate}[sys.argv[1]]()

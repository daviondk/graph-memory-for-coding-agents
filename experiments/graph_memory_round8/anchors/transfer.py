"""Evaluate the fixed memory on held-out refactoring types including actual inlining."""
import collections
import json
import re
import sys
from prepare import CACHE, ROOT, git, hashbytes, load, parse_label, save
from predict import front, locate, predict, tag
from route import mapped_line, snapshot
from score import confident


def prepare():
    data = json.loads((CACHE/"python-data.json").read_bytes())
    q, labels, counts = [], {}, collections.Counter()
    kinds = {"Inline Method", "Pull Up Method", "Push Down Method"}
    for change in data:
        refs = [ref for ref in change["refactorings"] if ref["type"] in kinds and ref["validation"]=="TP"]
        if not refs:
            continue
        project = change["repository"].removeprefix("https://github.com/").removesuffix(".git")
        commit = change["sha1"]
        parents = git(project,"rev-list","--parents","-n","1",commit).decode().split()[1:]
        for ref in refs:
            desc = ref["description"]
            if len(parents)!=1 or re.search(r"exploit|malware|ransom|vulnerability|penetration|cve-|secret_key_agreement",desc,re.I):
                counts["excluded"]+=1
                continue
            if ref["type"]=="Inline Method":
                pattern = r"Inline Method \w+ ([\w$]+)\(.*?\) inlined to \w+ ([\w$]+)\(.*?\) in class (\S+)"
                m = re.fullmatch(pattern, desc)
                assert m, desc
                old, new, owner, other = m[1],m[2],m[3],m[3]
            else:
                pair = parse_label(ref)
                assert pair, desc
                old, owner, new, other = pair
            cid = hashbytes((project+commit+desc).encode())[:18]
            assert cid not in labels
            q.append(dict(case=cid,project=project,commit=commit,before=parents[0],name=old,scope=owner))
            labels[cid] = dict(name=new,scope=other,kind=ref["type"])
    save("transfer-queries.json",q)
    save("transfer-labels.json",labels)
    save("transfer-source.json",dict(n=len(q),excluded=dict(counts)))


def forecasts():
    q = load("transfer-queries.json")
    out, pools = [],{}
    for r in q:
        cid, commit, project = r["case"], r["commit"], r["project"]
        if commit not in pools:
            old,new,_ = front(project,r["before"],commit)
            _,mapping = snapshot(project,r["before"],commit)
            pools[commit] = old,new,mapping
        old,new,mapping = pools[commit]
        ix = locate(old,r["name"],r["scope"])
        pred = dict(case=cid,commit=commit,n_old=len(ix),project=project)
        out.append(pred)
        if len(ix)!=1:
            continue
        src = old[ix[0]]
        peers = [f for f in old if f["path"]==src["path"]]
        ranks, scores, _ = predict(src,peers,new)
        targetpath, changes = mapping.get(src["path"], (src["path"],[]))
        line = mapped_line(src["line"], changes)
        def pos(i):
            f = new[i]
            return (f["path"]!=targetpath, abs(f["line"]-line) if f["path"]==targetpath else 10**9,
                f["name"]!=src["name"], f["qual"].rpartition(".")[0]!=src["qual"].rpartition(".")[0], tag(f))
        vocab=collections.Counter(g for f in peers for g in f["grams"][0])
        hashes=set(sorted(src["grams"][0],key=lambda g:(vocab[g],g))[:8])
        rr=[len(hashes&f["grams"][0]) for f in new]
        allidx=range(len(new))
        rank=dict(git=sorted(allidx,key=pos),rarelex=ranks["rarelex"],
            hybrid=sorted(allidx,key=lambda i:(-rr[i],pos(i))),mixed=ranks["mixed"])
        pred.update(pool=[tag(f) for f in new],old_address=tag(src),top={k:(v[0] if v else None) for k,v in rank.items()},
                    accepted=confident(scores),verified=confident(scores))
        if pred["accepted"]:
            lead=new[rank["mixed"][0]]
            olds=[f for f in old if (f["path"],f["qual"])==(lead["path"],lead["qual"])]
            foreign=(src["path"],src["qual"])!=(lead["path"],lead["qual"])
            pred["verified"]=not (foreign and len(olds)==1 and bool(lead["grams"][0]) and olds[0]["grams"][0]==lead["grams"][0])
    save("transfer-predictions.json",out)
    names=["TRANSFER.md","transfer.py","transfer-queries.json","transfer-predictions.json","predict.py","route.py","score.py"]
    save("transfer-lock.json",{n:hashbytes((ROOT/n).read_bytes()) for n in names})


def evaluate():
    for name, h in load("transfer-lock.json").items():
        assert hashbytes((ROOT/name).read_bytes())==h
    labels,raw=load("transfer-labels.json"),load("transfer-predictions.json")
    main_commits = {r["commit"] for r in load("outcomes.json")}
    summary=collections.Counter(); cats=collections.defaultdict(collections.Counter); out=[]
    for r in raw:
        gold=labels[r["case"]]
        g=cats[gold["kind"]]
        g["before_resolution"]+=1
        summary["queries"]+=1
        if r["n_old"]!=1:
            g["unresolved_old"]+=1
            continue
        funcs=[dict(name=qual.split(".")[-1],qual=qual,path=p,line=l) for p,qual,l in r["pool"]]
        same=[f for f in funcs if f["path"]==r["old_address"][0] and f["qual"]==r["old_address"][1]]
        negative=gold["kind"]=="Inline Method"
        if negative and same:
            g["ambiguous_survival"]+=1
            continue
        ix=locate(funcs,gold["name"],gold["scope"])
        correct={name: bool(not negative and len(ix)==1 and i==ix[0]) for name,i in r["top"].items()}
        g["n"]+=1
        if not negative and len(ix)!=1:
            g["unresolved_new"]+=1
        for name,val in correct.items():
            g[name]+=int(val)
        g["accepted"]+=r["accepted"]
        g["accepted_correct"]+=r["accepted"] and correct["mixed"]
        g["verified"]+=r["verified"]
        g["verified_correct"]+=r["verified"] and correct["mixed"]
        out.append(dict(case=r["case"],commit=r["commit"],kind=gold["kind"],correct=correct,accepted=r["accepted"],verified=r["verified"]))
    commits={r["commit"] for r in out}
    result=dict(n=len(out),commits=len(commits),overlapping_main_commits=len(commits & main_commits),counts=summary,groups=cats)
    save("transfer-outcomes.json",out)
    save("transfer-results.json",result)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    {"prepare":prepare,"predict":forecasts,"score":evaluate}[sys.argv[1]]()

"""Classify a proposed successor as a possible former caller, using observable calls."""
import ast
import collections
import functools
import gzip
import json
import warnings
from prepare import ROOT,git,load,save
warnings.filterwarnings("ignore",category=SyntaxWarning)


@functools.lru_cache(maxsize=300)
def definitions(project,rev,path):
    raw=git(project,"ls-tree","-z",rev,"--",path)
    if not raw:
        return {}
    oid=raw.split(b"\t",1)[0].split()[2].decode()
    try:
        tree=ast.parse(git(project,"cat-file","blob",oid))
    except (ValueError,SyntaxError,UnicodeError):
        return {}
    out=collections.defaultdict(list)
    def calls(n,names):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):
            return
        if isinstance(n,ast.Call):
            f=n.func
            if isinstance(f,ast.Name):
                names.add(f.id)
            elif isinstance(f,ast.Attribute):
                names.add(f.attr)
        for child in ast.iter_child_nodes(n):
            calls(child,names)
    def visit(n,stack):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            stack=stack+(n.name,)
            if not isinstance(n,ast.ClassDef):
                names=set()
                for stmt in n.body:
                    calls(stmt,names)
                out[".".join(stack)].append((n.lineno,names))
        for child in ast.iter_child_nodes(n):
            visit(child,stack)
    visit(tree,())
    return out


def flag(project,old,new,origin,winner):
    path,qual,_=origin
    dest,other,lineno=winner
    if (path,qual)==(dest,other) or qual in definitions(project,new,path):
        return False
    earlier=definitions(project,old,dest).get(other,[])
    if len(earlier)!=1:
        return False
    current=[calls for line,calls in definitions(project,new,dest).get(other,[]) if line==lineno]
    name=qual.split(".")[-1]
    return len(current)==1 and name in earlier[0][1] and name not in current[0]


def main():
    old={r["case"]:r for r in load("queries.json")}
    ident={r["case"]:r for r in load("identity-cases.json")}
    pools=json.loads(gzip.decompress((ROOT/"pools.json.gz").read_bytes()))
    out=[]
    for line in gzip.decompress((ROOT/"rankings.jsonl.gz").read_bytes()).splitlines():
        r=json.loads(line)
        cid=r["case"]
        q=old[cid]
        verdict=ident[cid]["actual"]
        winner=pools[r["commit"]]["candidates"][r["rankings"]["mixed"][0]]
        signal=verdict["verified"] and flag(q["project"],q["old"],q["new"],r["origin"],winner)
        out.append(dict(case=cid,commit=r["commit"],group="Rename / Move",accepted=verdict["verified"],
                    correct=verdict["correct"],flag=signal,recipient_correct=None,winner=winner))
    tqueries={r["case"]:r for r in load("transfer-queries.json")}
    tlabels=load("transfer-labels.json")
    tpred={r["case"]:r for r in load("transfer-predictions.json")}
    from predict import locate
    for r in load("transfer-outcomes.json"):
        cid=r["case"]
        q=tqueries[cid]; p=tpred[cid]; l=tlabels[cid]
        idx=p["top"]["mixed"]; winner=p["pool"][idx]
        signal=p["verified"] and flag(q["project"],q["before"],q["commit"],p["old_address"],winner)
        funcs=[dict(path=a,qual=b,name=b.split(".")[-1],line=c) for a,b,c in p["pool"]]
        ix=locate(funcs,l["name"],l["scope"])
        recipient=(len(ix)==1 and ix[0]==idx) if r["kind"]=="Inline Method" else None
        out.append(dict(case=cid,commit=r["commit"],group=r["kind"],accepted=p["verified"],correct=r["correct"]["mixed"],
               flag=signal,recipient_correct=recipient,winner=winner))
    agg={}
    for group in dict.fromkeys(r["group"] for r in out):
        g=[r for r in out if r["group"]==group]
        agg[group]=dict(n=len(g),accepted=sum(r["accepted"] for r in g),
            correct_accepted=sum(r["accepted"] and r["correct"] for r in g),flagged=sum(r["flag"] for r in g),
            retained=sum(r["accepted"] and not r["flag"] for r in g),
            lost_correct=sum(r["flag"] and r["correct"] for r in g),
            recipient_correct=sum(r["recipient_correct"] is True for r in g),
            flagged_correct_recipient=sum(r["flag"] and r["recipient_correct"] is True for r in g))
    save("call-edge-cases.json",out)
    save("call-edge-results.json",agg)
    print(json.dumps(agg,indent=2))
if __name__=="__main__":
    main()

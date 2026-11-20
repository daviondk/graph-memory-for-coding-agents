"""Evaluate frozen reuse decisions against a fresh AST walk of each subsequent wheel."""
import ast
import json
import random
import statistics
import warnings
from collections import Counter,defaultdict
from common import ROOT, POLICIES, modules, digest, dump, fingerprint

warnings.filterwarnings("ignore",category=SyntaxWarning)
FUN=(ast.FunctionDef,ast.AsyncFunctionDef)
def oracle(raw):
    if raw is None:return {}, "deleted"
    try:
        tree=ast.parse(raw)
    except (SyntaxError,ValueError,UnicodeError):
        return {}, "parse_error"
    funcs=[x for x in tree.body if isinstance(x,FUN)]
    counts=Counter(x.name for x in funcs)
    byname={x.name:x for x in funcs if counts[x.name]==1}
    sigs={}
    for name,x in byname.items():
        sigs[name]=fingerprint([x.__class__.__name__,ast.dump(x.args),ast.dump(x.returns) if x.returns is not None else None,
                                list(map(ast.dump,getattr(x,"type_params",())))])
    labels={}
    for name,x in byname.items():
        pending=list(x.body); found=set()
        while pending:
            node=pending.pop()
            if isinstance(node,(*FUN,ast.ClassDef,ast.Lambda)):continue
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id!=name and node.func.id in byname:
                found.add(node.func.id)
            pending.extend(ast.iter_child_nodes(node))
        labels[name]=fingerprint([(c,sigs[c]) for c in sorted(found)])
    return labels, "parsed"
def main():
    lock=json.loads((ROOT/"prediction-lock.json").read_bytes())
    for f,h in lock["files"].items():assert digest((ROOT/f).read_bytes())==h,f
    sources={(x["project"],x["version"]):x["name"] for x in json.loads((ROOT/"sources.json").read_bytes())}
    grouped=defaultdict(list)
    for ln in (ROOT/"decisions.jsonl").read_text("utf8").splitlines():
        row=json.loads(ln);grouped[row["project"],row["new"]].append(row)
    n_by=Counter(); groups={}; files={q:set() for q in POLICIES}
    all_rows=0; flip=0; new_status=Counter()
    deltas=defaultdict(Counter)
    with (ROOT/"outcomes.jsonl").open("w",encoding="utf8",newline="\n") as out:
        for (project,ver),xs in grouped.items():
            data=modules(sources[project,ver]);seen={}
            if project not in groups:groups[project]={p:Counter() for p in POLICIES}
            for row in xs:
                key=row["path"]
                if key not in seen:seen[key]=oracle(data.get(key))
                labels,status=seen[key]
                new=labels.get(row["caller"]);same=new==row["old_answer"]
                assert not row["reuse"]["dependencies"] or row["reuse"]["headers"]
                new_status[status]+=1;flip+=int(not same)
                for pol,y in row["reuse"].items():
                    result="correct_reuse" if y and same else "stale" if y else "reread"
                    groups[project][pol][result]+=1
                    if not y:files[pol].add((project,ver,key))
                if row["reuse"]["headers"] and not row["reuse"]["dependencies"]:
                    deltas[project]["valid" if same else "stale"]+=1
                out.write(json.dumps(dict(project=project,new=ver,path=key,caller=row["caller"],same=same,
                                          new_answer=new,source_status=status),separators=(",",":"))+"\n")
                n_by[project]+=1;all_rows+=1
    assert sum(n_by.values())==lock["total"]
    totals={}
    for pol in POLICIES:
        d=sum((groups[k][pol] for k in groups),Counter())
        totals[pol]={**{item:d[item] for item in ("correct_reuse","stale","reread")},"distinct_files_to_open":len(files[pol])}
        assert sum(d.values())==all_rows
    effects=[deltas[project]["valid"]/n for project,n in sorted(n_by.items())]
    assert len(effects)==8
    rng=random.Random(70631)
    boot=sorted(statistics.mean(rng.choices(effects,k=len(effects))) for _ in range(10000))
    summary=dict(n=all_rows,n_projects=len(groups),projects=dict(n_by),changed_answers=flip,source_status=dict(new_status),
        policies=totals,by_project=groups,primary_gain_project_macro=statistics.mean(effects),
        ci=[boot[249],boot[9749]],extra_by_project=deltas,rows_sha256=digest((ROOT/"outcomes.jsonl").read_bytes()))
    dump("results.json",summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("by_project","extra_by_project","rows_sha256")},indent=2))
if __name__=="__main__":main()

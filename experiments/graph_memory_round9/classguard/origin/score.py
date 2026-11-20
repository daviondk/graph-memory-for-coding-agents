"""Evaluate the fixed schema rule using only old discovery observations for each query."""
import ast
import collections
import gzip
import hashlib
import json
from pathlib import Path
from collect_types import ROOT,PANELS


def static_layout(text):
    tree=ast.parse(text)
    out={}
    def visit(node,parents):
        if isinstance(node,ast.ClassDef):
            here=parents+(node.name,)
            sig=[*map(ast.dump,node.bases),*map(ast.dump,node.keywords),*map(ast.dump,node.decorator_list)]
            sig.extend(ast.dump(v) for v in node.body if isinstance(v,(ast.Assign,ast.AnnAssign,ast.AugAssign)))
            out[".".join(here)]=sig
            parents=here
        elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            parents=parents+(node.name,)
        for child in ast.iter_child_nodes(node):visit(child,parents)
    visit(tree,())
    return out


def main():
    rows=[]
    for panel in PANELS:
        src=ROOT.parents[1]/panel
        outcomes=json.loads((src/"outcomes.json").read_bytes())
        for task in sorted({r["task"] for r in outcomes}):
            folder=src/"runs"/task
            code=json.loads(gzip.decompress((folder/"change.json.gz").read_bytes()))
            schemas=set()
            for path,before in code["before"].items():
                a,b=static_layout(before),static_layout(code["after"][path])
                schemas.update(path+"|"+k for k in a.keys()|b.keys() if a.get(k)!=b.get(k))
            for direction,old in (("fix","base"),("revert","gold")):
                rec=json.loads((ROOT/panel/task/(old+".json")).read_bytes())["records"]
                nodes=sorted(rec)
                for r in outcomes:
                    if (r["task"],r["direction"])!=(task,direction):continue
                    node=r["node"];past=rec[node]
                    shuffled=rec[nodes[(nodes.index(node)+1)%len(nodes)]]
                    tm=r["selected"]["testmon"]
                    flags=dict(testmon=tm,any_shape=tm or bool(schemas),direct=tm or bool(schemas&set(past["direct"])),
                            ancestry=tm or bool(schemas&set(past["ancestors"])),shuffled=tm or bool(schemas&set(shuffled["ancestors"])))
                    rows.append(dict(panel=panel,task=task,direction=direction,node=node,outcome_changed=r["changed"],old_status=r["prior"],
                        selected=flags,changed_class=sorted(schemas),old_mro=sorted(schemas&set(past["ancestors"])),
                        old_direct=sorted(schemas&set(past["direct"])),n_recorded=len(past["ancestors"])))
    total={}
    for panel in PANELS:
        by={}
        for direction in ("fix","revert"):
            g=[r for r in rows if r["panel"]==panel and r["direction"]==direction]
            conditions={k:dict(reruns=sum(r["selected"][k] for r in g),stale=sum(not r["selected"][k] and r["outcome_changed"] for r in g))
                        for k in g[0]["selected"]}
            by[direction]=dict(n=len(g),issues=len({r["task"] for r in g}),schema_issues=len({r["task"] for r in g if r["changed_class"]}),
                        conditions=conditions)
        total[panel]=by
    for name,obj in (("rows.json",rows),("results.json",total)):
        (ROOT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    files=[ROOT/p for p in ("PROTOCOL.md","score.py","collect_types.py","observe.py","rows.json","results.json")]
    files.extend(p for panel in PANELS for p in (ROOT/panel).glob("*/*.json"))
    (ROOT/"verification.json").write_text(json.dumps({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2)+"\n")
    print(json.dumps(total))
if __name__=="__main__":main()

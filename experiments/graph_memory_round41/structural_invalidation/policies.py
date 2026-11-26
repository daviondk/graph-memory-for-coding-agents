"""Source-symbol footprints, location remapping, and exact content lookup."""
import ast
from collections import Counter,defaultdict
import warnings

from shared import h,SemanticStore


def index_python(text):
    """Only opaque lexical paths, source intervals and content digests survive parsing."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree=ast.parse(text)
    except (SyntaxError,ValueError,RecursionError,MemoryError) as exc:
        return {"valid":False,"reason":type(exc).__name__,"nodes":[],"unique":{}}
    lines=text.split("\n")
    nodes=[]
    stack=[(tree,())]
    while stack:
        node,scope=stack.pop()
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            scope=scope+((type(node).__name__,node.name),)
            kind=".".join(k+":"+n for k,n in scope)
            low=min([node.lineno]+[deco.lineno for deco in node.decorator_list])
            high=node.end_lineno
            key=h(kind);body=h("\n".join(lines[low-1:high]))
            nodes.append((low,high,key,body))
        stack.extend((child,scope) for child in ast.iter_child_nodes(node))
    counts=Counter(x[2] for x in nodes)
    # Increasing width yields the innermost containing scope. Equal-width distinct nodes are ambiguous.
    ordered=sorted(nodes,key=lambda x:(x[1]-x[0],x[0],x[2]))
    return {"valid":True,"reason":"ok","nodes":ordered,"unique":{r[2]:r for r in nodes if counts[r[2]]==1}}


def ast_map(path,old,new,blocks):
    sym="symbol:"+path+":"
    if not old["valid"] or not new["valid"]:
        cut=[b[0] for b in blocks if SemanticStore._entity_affected("file:"+path,("file:"+path,))]
        return {},{str(i):"file_fallback" for i in cut},0
    prior=old["unique"];current=new["unique"]
    identical={k for k,v in prior.items() if k in current and current[k][3]==v[3]}
    # The conservative sentinel represents any block crossing a lexical boundary or lacking a stable owner.
    changes=(sym+"WHOLE",)+tuple(sym+k for k in sorted(set(prior)-identical))
    survivors={};reason={};with_owner=0
    for i,lo,hi in blocks:
        candidates=[n for n in old["nodes"] if n[0]<=lo and hi<=n[1]]
        if not candidates:
            tag="WHOLE";why="no_owner"
        elif (len(candidates)>1 and candidates[0][1]-candidates[0][0]==candidates[1][1]-candidates[1][0]) or candidates[0][2] not in prior:
            tag="WHOLE";why="ambiguous_owner"
        else:
            tag=candidates[0][2];with_owner+=1
            why="changed_or_missing" if tag not in identical else "unchanged_symbol"
        affected=SemanticStore._entity_affected(sym+tag,changes)
        assert affected == (tag not in identical)
        if affected:
            reason[str(i)]=why
        else:
            shift=current[tag][0]-prior[tag][0]
            survivors[str(i)]=[lo+shift,hi+shift]
    return survivors,reason,with_owner


def content_map(old_lines,new_lines,visible,blocks):
    before=list(map(h,old_lines));after=list(map(h,new_lines));post=defaultdict(list)
    for i,item in enumerate(after):post[item].append(i)
    survivors={};refused={}
    for i,lo,hi in blocks:
        want=[visible[n] for n in range(lo,hi+1)]
        if not (0<lo<=hi<=len(before)) or before[lo-1:hi]!=want:
            refused[str(i)]="prior_mismatch";continue
        # Start with the rarest line to limit candidate probes. All lines and boundaries must match exactly.
        at=min(range(len(want)),key=lambda j:len(post[want[j]]))
        starts=[]
        for pos in post[want[at]]:
            off=pos-at
            if off>=0 and off+len(want)<=len(after) and after[off:off+len(want)]==want:
                starts.append(off)
                if len(starts)==2:break
        if len(starts)==1:
            survivors[str(i)]=[starts[0]+1,starts[0]+len(want)]
        else:
            refused[str(i)]="absent" if not starts else "multiple"
    return survivors,refused


"""Compute reuse decisions from one past execution and an observed source delta."""
import ast
import collections
import difflib
import functools
import gzip
import hashlib
import json
import warnings
from collect import ROOT,RUNS,AGENT,read,save,digest
warnings.filterwarnings("ignore",category=SyntaxWarning)


def packed(p,obj):
    p.write_bytes(gzip.compress(json.dumps(obj,separators=(",",":"),sort_keys=True).encode(),mtime=0))


def unpack(p):
    return json.loads(gzip.decompress(p.read_bytes()))


@functools.lru_cache(maxsize=250)
def scope_map(source):
    mapping=["<module>"]*(len(source.splitlines())+1)
    try:
        tree=ast.parse(source)
    except (ValueError,SyntaxError,UnicodeError):
        return mapping
    def visit(n,path):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            path=path+(n.name,)
            scope=".".join(path)
            for lineno in range(n.body[0].lineno,n.end_lineno+1):
                mapping[lineno]=scope
        elif isinstance(n,ast.ClassDef):
            path=path+(n.name,)
        for child in ast.iter_child_nodes(n):
            visit(child,path)
    visit(tree,())
    return mapping


def keys_for_change(before,after):
    touched=set()
    lines={}
    for path,a in before.items():
        b=after[path]
        if a==b:
            continue
        amap,bmap=scope_map(a),scope_map(b)
        linenos=set()
        for op,lo,hi,lo2,hi2 in difflib.SequenceMatcher(None,a.splitlines(),b.splitlines(),autojunk=False).get_opcodes():
            if op=="equal":continue
            for n in range(lo+1,hi+1):
                touched.add(path+"|"+amap[n]);linenos.add(n)
            if lo==hi:
                linenos.update(n for n in (lo,lo+1) if 0<n<len(amap))
            for n in range(lo2+1,hi2+1):
                touched.add(path+"|"+bmap[n])
        lines[path]=linenos
    return touched,lines


def observed(task,side,changes,contexts):
    keys=collections.defaultdict(set)
    byfile=collections.defaultdict(dict)
    for ctx,mapping in contexts.items():
        for path,lines in mapping.items():
            byfile[path][ctx]=lines
    for path,mapping in byfile.items():
        if path in changes:
            src=changes[path]
        else:
            src=(AGENT/"tasks"/task/"base"/path).read_text(encoding="utf8")
        idx=scope_map(src)
        for ctx,lines in mapping.items():
            keys[ctx].update(path+"|"+idx[n] for n in lines if 0<n<len(idx))
    return keys


@functools.lru_cache(maxsize=150000)
def bloom_mask(key,bits):
    h=hashlib.blake2b(key.encode(),digest_size=16,person=b"R9test").digest()
    mask=0
    for i in range(0,16,4):
        mask|=1<<(int.from_bytes(h[i:i+4],"big")%bits)
    return mask


def bloom(keys,bits):
    mask=0
    for k in keys:mask|=bloom_mask(k,bits)
    return mask


def possibly_contains(mask,queries,bits):
    return any(mask&bloom_mask(q,bits)==bloom_mask(q,bits) for q in queries)


def status(reports):
    if any(out=="failed" and phase in ("setup","teardown") for phase,out,_ in reports):return "error"
    for phase,out,_ in reports:
        if phase=="call":return out
    return "unresolved"


def main():
    rows=[];costs=[];graphs=[]
    for task in read(ROOT/"collection-inputs.json")["ids"]:
        folder=RUNS/task
        code=unpack(folder/"change.json.gz")
        for side,other,direction in (("base","gold","fix"),("gold","base","revert")):
            old=unpack(folder/(side+".json.gz"))
            src=code["before" if side=="base" else "after"]
            dst=code["after" if side=="base" else "before"]
            touched,change_lines=keys_for_change(src,dst)
            edges=observed(task,side,src,old["contexts"])
            common=edges["shared"];contexts=old["contexts"]
            nodes=read(folder/"nodes.json")
            g={k:sorted(v) for k,v in edges.items()}
            graphs.append(dict(task=task,direction=direction,changed=sorted(touched),edges=g))
            compact={k:sorted(v-common) for k,v in edges.items() if k!="shared"}
            compact["shared"]=sorted(common)
            graph_bytes=len(gzip.compress(json.dumps(compact,separators=(",",":"),sort_keys=True).encode(),mtime=0))
            costs.append(dict(task=task,direction=direction,tests=len(nodes),shared_keys=len(common),
                     separate_256B=len(nodes)*256,shared_only_gzip=len(gzip.compress(json.dumps(sorted(common),separators=(",",":")).encode(),mtime=0)),
                     observed_factored_gzip=graph_bytes))
            for node in nodes:
                local=edges[node]
                allkeys=local|common
                prior=status(old["reports"].get(node,[]))
                test_lines=contexts.get(node,{})
                shared_lines=contexts.get("shared",{})
                files=set(test_lines)|set(shared_lines)
                old_failed=prior=="failed"
                exact=bool(touched&allkeys)
                d=dict(always=True,reuse=False,failed=old_failed,file=bool(set(change_lines)&files),symbol=exact,
                       lines=any(ls.intersection(test_lines.get(p,[])) or ls.intersection(shared_lines.get(p,[])) for p,ls in change_lines.items()))
                for bits in (512,2048):
                    d["bloom"+str(bits)]=possibly_contains(bloom(allkeys,bits),touched,bits)
                    d["shared"+str(bits)]=bool(common&touched) or possibly_contains(bloom(local-common,bits),touched,bits)
                    assert not exact or d["bloom"+str(bits)] and d["shared"+str(bits)]
                d.update({k+"_or_failed":v or old_failed for k,v in list(d.items()) if k in ("symbol","bloom2048","shared2048","lines")})
                rows.append(dict(task=task,direction=direction,node=node,prior=prior,selected=d,dynamic_symbols=len(local),
                        common_symbols=len(common),changed_symbols=len(touched),old_affected=sorted(allkeys&touched)))
    packed(ROOT/"forecasts.json.gz",rows);packed(ROOT/"graphs.json.gz",graphs);save(ROOT/"storage.json",costs)
    files=["PROTOCOL.md","collection-inputs.json","predict.py","forecasts.json.gz","graphs.json.gz","storage.json"]
    save(ROOT/"prediction-lock.json",{f:digest((ROOT/f).read_bytes()) for f in files})
    print(len(rows),"decisions")
if __name__=="__main__":
    main()

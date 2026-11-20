"""Gold-free historical receipts, source identifiers, and serialization."""
from pathlib import Path
import gzip,hashlib,json,sys
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
UP=WORK/"graph_memory_round6/published"
R9=WORK/"graph_memory_round9"
PANELS={"primary":R9/"testmemory_compat","holdout":R9/"testmemory_holdout"}
ORIG={"primary":WORK/"graph_memory_round8/agent","holdout":WORK/"graph_memory_round7/reader"}
def sha(b):return hashlib.sha256(b).hexdigest()
def fh(p):return sha(p.read_bytes())
def packed(x):return json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(",",":")).encode()
def put(p,x):
    b=gzip.compress(packed(x),mtime=0) if p.suffix==".gz" else (json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()
    p.write_bytes(b)
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def status(reports,node):
    phases=reports.get(node,[])
    if any(out=="failed" and p in ("setup","teardown") for p,out,*_ in phases):return "error"
    calls=[x[1] for x in phases if x[0]=="call"]
    return calls[0] if len(calls)==1 else "unresolved"
def initial():
    from subprocess import check_output
    sys.path.insert(0,str(R9/"budget"));import sketch
    records=[];receipts={}
    for panel,base in PANELS.items():
        for filename in ["graphs.json.gz","collection-inputs.json","runtime-freeze.txt"]:
            receipts[(base/filename).relative_to(WORK).as_posix()]=fh(base/filename)
        for g in get(base/"graphs.json.gz"):
            task,direction=g["task"],g["direction"];side="base" if direction=="fix" else "gold"
            old=base/"runs"/task/(side+".json.gz");old_info=get(old)
            roster=base/"runs"/task/"nodes.json";nodes=sorted(get(roster))
            src=ORIG[panel]/"tasks"/task/"grading.json"; cfg=get(src)
            base_commit=get(WORK/"graph_memory_round6/repair/transfer/tasks"/task/"public.json")["base_commit"]
            env=fh(base/"runtime-freeze.txt")
            versions=[sha(packed([task,base_commit,cfg["test_patch"],x,env])) for x in ("",cfg["patch"])]
            old_rev,new_rev=versions if direction=="fix" else versions[::-1]
            receipts[old.relative_to(WORK).as_posix()]=fh(old);receipts[src.relative_to(WORK).as_posix()]=fh(src)
            receipts[roster.relative_to(WORK).as_posix()]=fh(roster)
            edges=g["edges"];obs=[];sets=[]
            for n in nodes:
                s=status(old_info["reports"],n);assert s in ("passed","failed")
                obs.append(dict(node=n,prior=s,source_ref=sha(packed([fh(old),n,old_info["reports"][n]]))))
                sets.append(set(edges.get("shared",[]))|set(edges.get(n,[])))
            budget=256*len(nodes)
            layouts=sketch.layout(sets,budget);packets={}
            import base64
            for mode in ("fixed","selected"):
                data=sketch.encoded(layouts[mode],0);assert len(data)==budget
                packets[mode]=dict(data=base64.b64encode(data).decode(),sha256=sha(data),bytes=len(data))
            taskkey=panel+"/"+task+"/"+direction
            records.append(dict(key=taskkey,panel=panel,task=task,direction=direction,old=old_rev,new=new_rev,
                                base_git=base_commit,items=obs,changed=g["changed"],packets=packets,
                                expected_impact=[bool(s&set(g["changed"])) for s in sets]))
    put(ROOT/"inputs.gz",records)
    commit=check_output(["git","-C",str(UP/"MemTrace"),"rev-parse","HEAD"],text=True).strip()
    assert commit=="5508f8be81025d8aa90726b1e06aef4ea484e577"
    put(ROOT/"input-lock.json",dict(commit=commit,inputs=fh(ROOT/"inputs.gz"),sources=receipts,prior_code=fh(R9/"budget/sketch.py"),
                protocol=fh(ROOT/"PROTOCOL_RU.md"),adaptor=fh(ROOT/"common.py")))
    print(len(records),sum(len(r["items"]) for r in records))
if __name__=="__main__":initial()

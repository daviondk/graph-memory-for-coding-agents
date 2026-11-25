"""Classify effects of a disclosed faulty-source set using only structural observations."""
from collections import defaultdict,deque
from functools import lru_cache
from hashlib import sha256
from time import perf_counter_ns
from pathlib import Path
import gzip,json,re,sys
from fetch import P,D,SRC
from native import readl
def save(p,x):
    raw=(json.dumps(x,sort_keys=True,allow_nan=False,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw);return sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
@lru_cache(maxsize=50)
def rawfile(p):return readl(p)
def getcase(root,r):
    def filtered(path):
        rows=rawfile(root/path);task=r["task_id"];exact=[x for x in rows if x.get("task_id")==task]
        if exact:return exact
        m=re.search(r"(task_\d+)$",task);wanted={task,m[1]} if m else {task}
        return [x for x in rows if x.get("task_id") in wanted or x.get("original_task_id") in wanted]
    return filtered(r["paths"]["faulty_memories"]),filtered(r["paths"]["faulty_tracesteps"])
def primitive(mem,steps,diagnosis):
    allm={x["memory_id"] for x in mem};alls={x["step_id"] for x in steps};claims={x["step_id"] for x in steps if x["step_type"]=="claim"}
    assert allm.isdisjoint(alls) and set(diagnosis)<=allm
    parents=defaultdict(set)
    for m in mem:parents[m["memory_id"]].update(m.get("derived_from") or ())
    for s in steps:
        parents[s["step_id"]].update(s.get("used_ids") or ())
        for m in s.get("generated_memory_ids") or ():
            if m in allm:parents[m].add(s["step_id"])
    return parents,allm,claims
def fixed_scan(parents,src,mode):
    bad=set(src);inspections=0
    while True:
        delta=set()
        for k,dep in parents.items():
            if not dep or k in bad:continue
            inspections+=len(dep)
            if (dep<=bad if mode=="all" else dep&bad):delta.add(k)
        if not delta:return bad,inspections
        bad|=delta
def counted(parents,src,mode):
    children=defaultdict(list);need={}
    for v,ps in parents.items():
        need[v]=len(ps)
        for p in ps:children[p].append(v)
    z=set(src);q=deque(z);inspections=0
    while q:
        p=q.popleft()
        for v in children[p]:
            inspections+=1
            if v in z:continue
            need[v]-=1
            if mode=="any" or need[v]==0:z.add(v);q.append(v)
    return z,inspections
def main(panel):
    root=SRC/"data"/("controlled_benchmark" if panel=="controlled" else "adapted_lmev2_subset");rows=[]
    for r in readl(root/"registry.jsonl"):
        mem,steps=getcase(root,r);src=set(r["faulty_memory_ids"])
        mp=[{k:x.get(k) for k in ("memory_id","derived_from")} for x in mem]
        sp=[{k:x.get(k) for k in ("step_id","step_type","used_ids","generated_memory_ids")} for x in steps]
        parents,allm,claims=primitive(mp,sp,src)
        preds={"noop":set(),"source":src,"direct":src|{k for k in claims if parents[k]&src}};cost={}
        for mode in ("any","all"):
            s0=perf_counter_ns();out,ns=fixed_scan(parents,src,mode);s1=perf_counter_ns();out2,ni=counted(parents,src,mode);s2=perf_counter_ns()
            assert out==out2
            preds["reach_any" if mode=="any" else "rederive"]=out
            cost[mode]=dict(scan_checked_parent_slots_upper=ns,queue_edge_visits=ni,scan_ns=s1-s0,queue_index_build_and_run_ns=s2-s1)
        def opaque(x):return sha256((r["task_id"]+"\0"+x).encode()).hexdigest()
        op={opaque(k):{opaque(p) for p in ps} for k,ps in parents.items()};os={opaque(k) for k in src}
        for mode,a in (("any","reach_any"),("all","rederive")):assert counted(op,os,mode)[0]=={opaque(k) for k in preds[a]}
        blind={"m":mp,"s":sp,"diagnosis":sorted(src)}
        fp=sha256(json.dumps(blind,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        rows.append(dict(task=r["task_id"],domain=r["domain"],case=r["case_id"],diagnosis=sorted(src),blind_hash=fp,nm=len(mp),ns=len(sp),edges=sum(map(len,parents.values())),cost=cost,policies={k:dict(mem=sorted(z&allm),claims=sorted(z&claims)) for k,z in preds.items()}))
    assert len({r["task"] for r in rows})==len(rows)
    h=save(D/(panel+"-forecasts.json.gz"),rows);save(D/(panel+"-seal.json"),dict(n=len(rows),forecast_sha=h,source=sha256((D/"controls.py").read_bytes()).hexdigest(),protocol=sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest()))
    print(panel,len(rows),"sealed")
if __name__=="__main__":main(sys.argv[1])


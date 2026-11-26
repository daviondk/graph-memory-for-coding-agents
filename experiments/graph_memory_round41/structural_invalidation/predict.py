"""Seal same-pool selections prior to the independent new-version content check."""
from collections import Counter
import time

from shared import *
from policies import ast_map,content_map,index_python


def main():
    start=time.perf_counter();events,plans,views=inputs()
    projected={};cache={};root_cost={};run_roots=set()
    costs=Counter();scratch={"valid":False,"reason":"non_python","nodes":[],"unique":{}}
    def indexed(rev,text,rid):
        run_roots.add((rid,rev))
        if rev not in cache:
            stamp=time.perf_counter();cache[rev]=index_python(text);root_cost[rev]=time.perf_counter()-stamp
        return cache[rev]

    for key,row,is_py,old,new in stream(events):
        rid=row["run"];at=row["at"];path=row["path"];lo=row["start"];hi=row["end"];delta=row["delta"]
        before=old.split("\n");after=new.split("\n")
        assert len(after)-len(before)==delta
        plan,_=plans[rid][str(at)];rawview=views[rid][str(row["view"])]
        visible={n:ev for n,ev,*_ in rawview}
        pool=[(i,p,c,u) for i,p,l,h_,c,u,v in plan]
        blocks=[(i,l,h_) for i,p,l,h_,c,u,v in plan if p==path]
        assert all(v==row["view"] for i,p,l,h_,c,u,v in plan if p==path)
        old_ids,_,_=select(pool);assert list(old_ids)==row["old"]
        ts=time.perf_counter();beforebytes=old.encode("utf8");afterbytes=new.encode("utf8")
        raw_size=len(beforebytes)+len(afterbytes)
        oldhash=hashlib.sha256(beforebytes).hexdigest();newhash=hashlib.sha256(afterbytes).hexdigest()
        hash_seconds=time.perf_counter()-ts
        if is_py:
            A,B=indexed(oldhash,old,rid),indexed(newhash,new,rid)
            cold=root_cost[oldhash]+root_cost[newhash]
        else:
            A=B=scratch;cold=0
        t1=time.perf_counter()
        am,why,owners=ast_map(path,A,B,blocks)
        ast_lookup_s=time.perf_counter()-t1
        t2=time.perf_counter();cm,why_content=content_map(before,after,visible,blocks)
        content_s=time.perf_counter()-t2
        t3=time.perf_counter();rm={}
        for i,l,u in blocks:
            if u<lo:rm[str(i)]=[l,u]
            elif l>hi:rm[str(i)]=[l+delta,u+delta]
        range_lookup_s=time.perf_counter()-t3
        choices={};maps={"ast":am,"content":cm,"range":rm,"file":{}}
        dptime={}
        for policy,remain in maps.items():
            stamp=time.perf_counter()
            sol,_,_=select([v for v in pool if v[1]!=path or str(v[0]) in remain])
            dptime[policy]=time.perf_counter()-stamp;choices[policy]=list(sol)
        assert choices["range"]==row["interval"] and choices["file"]==row["file"]
        projected[key]=dict(run=rid,issue=row["issue"],held=row["held"],group=row["group"],changed=path,
            old=list(old_ids),choices=choices,maps=maps,ast_reasons=why,content_reasons=why_content,
            flags=dict(python=is_py,parsed=A["valid"] and B["valid"],parse_old=A["reason"],parse_new=B["reason"],
                       has_source=bool(isinstance(old,str) and isinstance(new,str)),owner_blocks=owners,edited_blocks=len(blocks)),
            cost=dict(bytes=raw_size,old_bytes=len(beforebytes),new_bytes=len(afterbytes),old=oldhash,new=newhash,
                      ast_cold_s=cold,ast_lookup_s=ast_lookup_s,range_lookup_s=range_lookup_s,
                      content_s=content_s,full_hash_s=hash_seconds,solver_s=dptime))
        if len(projected)%500==0:print("Ranked",len(projected),"of",len(events),flush=True)
    assert len(projected)==2696 and sum(v["held"] for v in projected.values())==1071
    save("predictions.json.gz",projected)
    save("forecast-seal.json",dict(events=len(projected),results=sha(D/"predictions.json.gz"),
          original=sha(G/"selections.json.gz"),plans=sha(G/"guarded-plans.json.gz"),
          views=sha(V/"visible.json.gz"),parquet_catalog=sha(RAW/"files.json"),
          external_rules=sha(SRC/"memtrace/semantic_memory/store.py"),run_seconds=time.perf_counter()-start,
          unique_python_versions=len(cache),within_run_distinct_versions=len(run_roots),
          unique_parse_seconds=sum(root_cost.values()),
          modeled_within_run_parse_seconds=sum(root_cost[root] for _,root in run_roots),
          program={p:sha(D/p) for p in ("PROTOCOL_RU.md","shared.py","policies.py","predict.py")}))
    print("Sealed",len(projected),"forecasts; unique parsed contents",len(cache),flush=True)


if __name__=="__main__":main()


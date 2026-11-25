from collections import Counter,defaultdict
from functools import lru_cache
from statistics import mean
import sys
from qcheck import D,rd,wr,sha,close
S=D.parent/"sequential_open";F=D.parent/"directional_open";sys.path.insert(0,str(F))
from dataset import c,ro,Tokenizer,TOK,CACHE
from analyse import targets
def merged(rs):
    out=[]
    for e,l,h in sorted(tuple(x) for x in rs):
        if h==l:continue
        if out and out[-1][0]==e and l<=out[-1][2]:out[-1]=(e,out[-1][1],max(out[-1][2],h))
        else:out.append((e,l,h))
    return out
def measure(v,g):
    return sum(max(0,min(h,b)-max(l,a)) for e,l,h in v for f,a,b in g if f==e)
def main():
    seq=rd(S/"sequence-lock.json");per=rd(S/"per-query.json.gz")["corpora"];res=rd(S/"results.json")["corpora"]
    report={}
    for name,code in (("isetrace","ise"),("multidoc","mdd")):
        pan=per[name];results=res[name];counts=defaultdict(Counter);toks=Tokenizer.from_file(str(TOK)) if code=="ise" else c.tok()
        @lru_cache(maxsize=100000)
        def head_len(e,l):return len(toks.encode(f"[{e}:{l}] ",add_special_tokens=False).ids)
        allrows={}
        for path,h in seq["files"].items():
            if (path.startswith("ise"))!=(code=="ise"):continue
            f=S/path;assert sha(f)==h
            for q,r in rd(f).items():r["_i"]=int(path[4]) if code=="ise" else None;allrows[q]=r
        getg=targets(code,{q:{"t":r["trace"] if code=="ise" else pan[q]["g"]} for q,r in allrows.items()})
        if code=="mdd":lookup={i:d[2] for i,d in enumerate(c.get_views()["documents"])}
        db=ro(D.parents[1]/"graph_memory_round23/read_causes/registry.sqlite") if code=="ise" else None
        grouped=defaultdict(list)
        for q,r in allrows.items():grouped[(r["_i"],r.get("trace",""))].append((q,r))
        for (i,t),records in grouped.items():
            if code=="ise":
                st=rd(CACHE/f"{i}-{t}.json.gz")["fields"];lookup={e:st[eid] for e,eid in db.execute("select e,eid from address where t=?",(t,))}
            for q,r in records:
                g=merged(getg[q][0]);gn=sum(b-a for _,a,b in g);base=merged(r["base"]);basechars=sum(b-a for _,a,b in base)
                def metric(xs):
                    vis=merged(base+[x[:3] for x in xs]);support=measure(vis,g)
                    return [int(support==gn),support/gn,sum(z[3] for z in xs),len(xs),len({z[0] for z in xs}),sum(b-a for _,a,b in vis)-basechars]
                def strict(xs,cap):
                    out=[];remaining=cap
                    for p in xs:
                        e,l,h,n=p
                        if remaining<head_len(e,l):break
                        if n<=remaining:out.append(p);remaining-=n;continue
                        head=f"[{e}:{l}] ";wire=head+lookup[e][l:h]
                        enc=toks.encode(wire,add_special_tokens=False);assert len(enc.ids)==n
                        cut=enc.offsets[remaining][0]
                        while cut>=len(head):
                            cost=len(toks.encode(wire[:cut],add_special_tokens=False).ids)
                            if cost<=remaining:break
                            cut-=1
                        if cut>=len(head):out.append([e,l,l+cut-len(head),cost])
                        break
                    return out
                for k,path in r["actions"].items():
                    assert len(path)<=4;visible=base
                    for e,l,h,n in path:
                        assert any(a==e and b==l for a,x,b in visible) and not any(a==e and x<=l<b for a,x,b in visible)
                        assert len(toks.encode(f"[{e}:{l}] "+lookup[e][l:h],add_special_tokens=False).ids)==n<=256 and h>l
                        visible=merged(visible+[[e,l,h]])
                    for j in range(1,5):
                        assert metric(path[:j])==pan[q]["steps"][k+"/"+str(j)]
                    cap=r["cap"][k];assert metric(cap)==pan[q]["steps"][k+"/cap"]
                    assert len(cap)<=len(path) and all(a==b for a,b in zip(cap[:-1],path))
                    if cap:assert cap[-1][:2]==path[len(cap)-1][:2] and cap[-1][2]<=path[len(cap)-1][2]
                    tiny=[op for op in cap if op[3]<head_len(op[0],op[1])]
                    assert all(op[1]==op[2] for op in tiny)
                    st=strict(path,768);old=metric(cap);new=metric(st);assert old[:2]==new[:2]
                    counts[k].update(full_paths=1,full_actions=len(path),cap_partial_headers=len(tiny),zero_body=sum(z[1]==z[2] for z in cap),
                                      cap_calls=old[3],cap_strict_calls=new[3],cap_tokens=old[2],cap_strict_tokens=new[2],cap_fs=old[0])
                for ctrl,(xs,ys) in r["equal"].items():
                    old=[metric(xs),metric(ys)]
                    assert old==[pan[q]["steps"]["tail_eq/"+ctrl],pan[q]["steps"]["control_eq/"+ctrl]] and old[0][2]==old[1][2]
                    tiny=sum(z[3]<head_len(z[0],z[1]) for seq2 in (xs,ys) for z in seq2)
                    if tiny:
                        cap=min(metric(strict(r["actions"][k],768))[2] for k in ("tail",ctrl))
                        while True:
                            ps=[strict(r["actions"][k],cap) for k in ("tail",ctrl)];new=list(map(metric,ps));nx=min(z[2] for z in new)
                            if new[0][2]==new[1][2]:break
                            assert nx<cap;cap=nx
                    else:new=old
                    counts["equal/"+ctrl].update(queries=1,old_paid=old[0][2],strict_paid=new[0][2],partial=tiny,changed_fs_first=new[0][0]-old[0][0],changed_fs_second=new[1][0]-old[1][0])
        if db:db.close()
        for k,a in results["summary"].items():
            arr=[v["steps"][k] for v in pan.values()]
            assert sum(z[0] for z in arr)==a["hits"]
            for j,field in enumerate(("coverage","tokens","calls","fields","new_chars"),1):assert close(mean(z[j] for z in arr),a[field])
        for k,cmp in results["paired"].items():
            x,y=k.split(" vs ");diff=[r["steps"][x][0]-r["steps"][y][0] for r in pan.values()]
            assert diff.count(1)==cmp["wins"] and diff.count(-1)==cmp["losses"] and close(mean(diff),cmp["delta"])
        report[name]=dict(counts)
    wr(D/"sequence-checks.json",report)
    print({k:{m:z.get("cap_partial_headers",z.get("partial")) for m,z in data.items()} for k,data in report.items()})
if __name__=="__main__":main()

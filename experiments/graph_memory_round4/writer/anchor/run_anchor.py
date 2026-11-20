"""Compare before/after anchoring on identical observable editor traces with a separately inverted future target."""
import gzip,json,hashlib,sys,time
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from shared import A,B,D,read,save,sha,rows,write,prior,printed
import importlib.util
spec=importlib.util.spec_from_file_location("r4_writer_experiment",D/"experiment.py"); core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
weights,paired=core.weights,core.paired
from transfer_followup import future_check
from context import line_target
from common import groups,success,rel,update_literal,newmeta

BASE_ADVANCE=prior.advance
COUNTS=Counter()
ARMS=["flat_original","flat_anchor","cap_original","cap_anchor"]

def unique_new(args,obs):
    new=args.get("new_str","")
    if not isinstance(new,str) or not new.strip():return None
    found=[]
    ls=printed(obs)
    for ns in groups(ls):
        block="\n".join(ls[n] for n in ns);pos=block.find(new)
        if pos<0:continue
        if block.find(new,pos+1)>=0:return None
        found.append((ns[0],block,pos))
    return found[0] if len(found)==1 else None

def invert(args,obs):
    m=unique_new(args,obs)
    if not m:return None
    first,block,pos=m;old=args["old_str"];new=args["new_str"]
    start=first+block[:pos].count("\n");original=block[:pos]+old+block[pos+len(new):]
    lines=original.split("\n");num=old.count("\n")+1
    values=lines[start-first:start-first+num]
    return (start,values) if len(values)==num else None

def anchored_advance(states,meta,event,t):
    _,args,obs=event;p=rel(args.get("path"));old=args.get("old_str");new=args.get("new_str","")
    if not success(args.get("command"),p,obs) or not isinstance(old,str) or not old or not isinstance(new,str):
        BASE_ADVANCE(states,meta,event,t);return
    before=states["rebase"].get(p,{})
    # Existing exact transport wins whenever available and consistent with the returned display.
    displayed=printed(obs)
    if not before or update_literal(before,old,new,displayed,t):
        BASE_ADVANCE(states,meta,event,t);return
    m=unique_new(args,obs)
    BASE_ADVANCE(states,meta,event,t)
    if not m:return
    first,block,pos=m
    lo=first+block[:pos].count("\n");hi=lo+old.count("\n");delta=new.count("\n")-old.count("\n")
    proposal={n+(delta if n>hi else 0):v for n,v in before.items() if n<lo or n>hi}
    if any(n in proposal and proposal[n][0]!=s for n,s in displayed.items()):
        COUNTS["conflicts_rejected"]+=1;return
    keep=states["rebase"].get(p,{})
    added={n:v for n,v in proposal.items() if n not in keep}
    if added:
        states["rebase"].setdefault(p,{}).update(added);COUNTS["successful_transports"]+=1
        COUNTS["preserved_line_observations"]+=len(added)

def current(method,states,blobs):
    if method.startswith("flat"):return states[method]["rebase"]
    return prior.materialize(prior.payload(blobs[method]))[1]["rebase"]

def factcheck(event,t,memory_a,memory_b,iid,step,seen,log):
    _,args,obs=event;p=rel(args.get("path"))
    if args.get("command")!="view" or not p:return
    for n,actual in printed(obs).items():
        a=memory_a.get(p,{}).get(n);b=memory_b.get(p,{}).get(n)
        if not b or a and a[0]==b[0]:continue
        token=(iid,p,step[p],n,b[0])
        if token in seen:continue
        seen.add(token)
        digest=lambda s:hashlib.sha256(s.encode()).hexdigest()
        log.append([iid,p,step[p],n,t,b[0]==actual,digest(b[0]),digest(actual)])

def predict(arg):
    panel,k=arg;src=A if panel=="A" else B;out=HERE/panel;ws=weights()
    validations=defaultdict(list);metrics=Counter()
    with gzip.open(out/f"cuts_{k}.gz","wt",encoding="utf8",compresslevel=2) as cf:
        for task in rows(src/f"source_{k}.jsonl.gz"):
            iid=task["instance"];const={"issue":task["issue"],"instance":iid}
            states={a:{"rebase":{}} for a in ARMS if a.startswith("flat")};metadata={a:newmeta() for a in states}
            blobs={a:prior.empty("lru") for a in ARMS if a.startswith("cap")};seen=defaultdict(set);version=Counter()
            for t,event in enumerate(task["events"],1):
                _,args,obs=event;p=rel(args.get("path"))
                if args.get("command")=="view":
                    for size in ("flat","cap"):
                        early=current(size+"_original",states,blobs);new=current(size+"_anchor",states,blobs)
                        factcheck(event,t,early,new,iid,version,seen[size],validations[size])
                if p and (success(args.get("command"),p,obs) or args.get("command") in ("insert","create","undo_edit")):version[p]+=1
                snaps={}
                for a in ARMS:
                    advance=anchored_advance if a.endswith("anchor") else BASE_ADVANCE
                    COUNTS.clear()
                    if a.startswith("cap"):
                        prior.advance=advance
                        try:blobs[a],_=prior.transition(blobs[a],event,const,ws,4096)
                        finally:prior.advance=BASE_ADVANCE
                        assert len(blobs[a])<=4096
                        metrics[a+"_byte_checks"]+=1
                    else:advance(states[a],metadata[a],event,t)
                    for name,count in COUNTS.items():metrics[a+"_"+name]+=count
                    if t%4==0 and t<len(task["events"]):
                        table=current(a,states,blobs)
                        # Timestamp-free visible data of each retained line. Save before looking at future commands.
                        snaps[a]=[[p,n,s] for p,vals in sorted(table.items()) for n,(s,age) in sorted(vals.items())]
                if snaps:write(cf,[iid,t,snaps])
    with gzip.open(out/f"verifications_{k}.gz","wt",encoding="utf8") as fp:
        for size,records in validations.items():
            for row in records:write(fp,[size,*row])
    return dict(metrics)

def grade(arg):
    panel,k=arg;src=A if panel=="A" else B;out=HERE/panel;cs=iter(rows(out/f"cuts_{k}.gz"));rs=[];audit=Counter()
    for task in rows(src/f"source_{k}.jsonl.gz"):
        iid=task["instance"];ev=task["events"]
        for t in range(4,len(ev),4):
            i,j,m=next(cs);assert (i,j)==(iid,t)
            args,obs=future_check(ev,t)
            if not args or not success(args.get("command"),rel(args.get("path")),obs):continue
            audit["accepted"]+=1
            gold=invert(args,obs)
            if not gold:
                audit["cannot_invert"]+=1;continue
            lo,texts=gold;p=rel(args["path"]);scores={};map0=None
            for a,items in m.items():
                table={n:s for path,n,s in items if path==p}
                if a=="flat_original":map0=table
                match=[table.get(lo+k)==s for k,s in enumerate(texts)]
                scores[a]=[int(all(match)),sum(match)/len(match),int(match[0])]
            # Independent forward localization of the exact old string, if available.
            pg=prior.pages({p:{n:(s,0) for n,s in map0.items()}})
            pos=line_target(pg,p,args["old_str"])
            if pos:
                ok=(pos[1]==lo and pos[2]==lo+len(texts)-1 and all(map0[lo+k]==s for k,s in enumerate(texts)))
                audit["forward_agrees" if ok else "forward_disagrees"]+=1
            rs.append([iid,task["official_repo"],t,len(texts),"inverted",scores])
    assert next(cs,None) is None
    return rs,audit

def main():
    mode=sys.argv[1];panels=["A","B"];args=[(p,k) for p in panels for k in range(8)]
    for p in panels:(HERE/p).mkdir(exist_ok=True)
    if mode=="predict":
        assert not (HERE/"checkpoint_lock.json").exists()
        fs=[HERE/"PROTOCOL_RU.md",HERE/"run_anchor.py",D/"experiment.py",D/"shared.py"]
        save(HERE/"method_lock.json",{str(p):sha(p) for p in fs})
        with ProcessPoolExecutor(3) as pool:data=list(pool.map(predict,args))
        save(HERE/"transports.json",dict((p,dict(sum((Counter(data[j]) for j,v in enumerate(args) if v[0]==p),Counter()))) for p in panels))
        save(HERE/"checkpoint_lock.json",{str(p.relative_to(HERE)):sha(p) for x in panels for p in (HERE/x).glob("*gz")})
    else:
        assert all(sha(HERE/n)==h for n,h in read(HERE/"checkpoint_lock.json").items())
        with ProcessPoolExecutor(3) as pool:data=list(pool.map(grade,args))
        report={}
        for panel in panels:
            indices=[j for j,(p,_) in enumerate(args) if p==panel];records=[r for j in indices for r in data[j][0]]
            au=sum((data[j][1] for j in indices),Counter())
            with gzip.open(HERE/panel/"scored.jsonl.gz","wt",encoding="utf8") as f:
                for row in records:write(f,row)
            check=defaultdict(list)
            for p in sorted((HERE/panel).glob("verifications_*.gz")):
                for size,*r in rows(p):check[size].append(r)
            report[panel]=dict(actions=len(records),audit=au,
                full={a:sum(r[-1][a][0] for r in records) for a in ARMS},
                ownership={s:paired(records,s+"_anchor",s+"_original") for s in ("cap","flat")},
                validation={s:dict(n=len(li),equal=sum(r[5] for r in li),conflicts=sum(not r[5] for r in li),issues=len({r[0] for r in li})) for s,li in check.items()})
        save(HERE/"results.json",report);print({p:(q["actions"],q["full"],q["validation"]) for p,q in report.items()})
if __name__=="__main__":main()


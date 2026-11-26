"""Transfer the frozen edit mapping rules to recorded SWE-agent interactions."""
from collections import Counter,defaultdict
import gzip,hashlib,importlib.util,json,re,sys
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1]
N=W/"graph_memory_round40/natural_invalidations"
sys.path.insert(0,str(W/"graph_memory_round27/code_boundary"))
from prepare import prod
sys.path.insert(0,str(N))
from score import select
from project import chunk
sys.path.insert(0,str(D.parent/"context_edits"))
from mechanism import match,project,tokens
def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def save(n,v):
    b=(json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(",",":"))+"\n").encode()
    (D/n).write_bytes(gzip.compress(b,mtime=0) if n.endswith(".gz") else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def path_of(a):
    path=a.get("path","").removeprefix("/testbed/").removeprefix("./")
    return path if prod(path) else ""
def lines(text):
    out={};last=None
    for line in text.split("\n"):
        m=re.fullmatch(r" *([0-9]+)\t(.*)",line)
        if not m:continue
        i=int(m[1]);s=m[2]
        if (last is not None and last+1!=i) or re.search(r"<response clipped>|<NOTE:|\.\.\.truncated|^\.{3}$",s,re.I):break
        out[i]=s;last=i
    return out
def locate(obs,lit):
    if not obs or not isinstance(lit,str) or not lit.strip():return None
    first=next(iter(obs));text="\n".join(obs.values());i=text.find(lit)
    if i<0 or text.find(lit,i+1)>=0:return None
    return first+text[:i].count("\n")
def sources():
    hand=W/"graph_memory_round37/code_visibility"
    assert sha(hand/"events.json.gz")==read(hand/"manifest.json")["files"]["events.json.gz"]
    exclude={r["issue"] for r in read(hand/"events.json.gz").values()}
    seen=set()
    for label in ("real_swe","real_swe_followup"):
        d=W/"graph_memory_round3"/label
        cat=read(d/"download_summary.json")
        for f in sorted(d.glob("source_*.jsonl.gz")):
            assert sha(f)==cat["sources"][f.name]
            with gzip.open(f,"rt",encoding="utf8") as io:
                for item in map(json.loads,io):
                    key=item["instance"];assert key not in seen;seen.add(key)
                    yield label,key,key in exclude,item
    assert len(seen)==293
def plan_for(active):
    rows=[];info={}
    for path,(t,hits,obs) in sorted(active.items(),key=lambda x:(-x[1][0],x[0])):
        facts=[(n,h(v),len(v.encode()),n+1 in obs) for n,v in obs.items()]
        for lo,hi,c in chunk(facts):
            i=len(rows);rows.append((i,path,c,1+32*min(8,hits)+128//(i+1)));info[i]=(path,lo,hi)
    return rows,info
def forecast():
    assert sha(D/"PROTOCOL_RU.md")=="81fa9a99b89053ee604764f6741d2e4875465b3b78f4726833e7040a1293b631"
    counters=Counter();out={};issue_info={}
    for panel,issue,duplicate,trace in sources():
        counters["all_issues"]+=1
        if duplicate:counters["overlap_excluded"]+=1;continue
        issue_info[h(issue)]=[panel,trace["official_repo"]]
        active={}
        for at,(tool,args,obs) in enumerate(trace["events"]):
            cmd=args.get("command");path=path_of(args)
            if tool=="other" or cmd not in ("view","str_replace","insert","create","undo_edit"):
                active.clear();continue
            if not path:continue
            now=lines(obs)
            if cmd=="view":
                if now:active[path]=(at,1+(active[path][1] if path in active else 0),now)
                continue
            if cmd!="str_replace" or not obs.startswith("The file snapshot has been edited."):
                active.pop(path,None);continue
            counters["successful_edits"]+=1
            if path not in active:continue
            counters["had_view"]+=1;rows,info=plan_for(active);before=active.pop(path)[2]
            old=list(select(rows)[0])
            if not any(info[i][0]==path for i in old):continue
            arg0=args.get("old_str");arg1=args.get("new_str")
            i0,i1=locate(before,arg0),locate(now,arg1);anchored=i0 is not None and i0==i1
            counters["primary"]+=1;counters["localized"]+=int(anchored)
            if anchored:
                start=i0;end=i0+arg0.count("\n");delta=arg1.count("\n")-arg0.count("\n")
                edge,interior,_=match(tokens(arg0),tokens(arg1))
            sels={};maps={}
            for mode in ("file","range","edges","local"):
                mapped={}
                for i,(p,lo,hi) in info.items():
                    if p!=path:continue
                    if mode=="file" or not anchored:continue
                    dst=project(lo,hi,start,end,delta,{"range":{},"edges":edge,"local":interior}[mode])
                    if dst is not None:mapped[i]=dst
                ids=list(select([r for r in rows if r[1]!=path or r[0] in mapped])[0])
                sels[mode]=ids
                maps[mode]=[[n-h0+dst[0],h(before[n])] for i in ids if i in mapped for p,h0,h1 in [info[i]] for dst in [mapped[i]] for n in range(h0,h1+1)]
            k=h(issue+"|"+str(at));out[k]=dict(issue=h(issue),repo=trace["official_repo"],panel=panel,at=at,path=h(path),anchored=anchored,old=old,sel=sels,maps=maps)
    save("forecasts.json.gz",out)
    save("forecast-seal.json",dict(rows=sha(D/"forecasts.json.gz"),issues=issue_info,counters=counters,program=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md")))
    print(counters)
def grade():
    from collections import defaultdict
    seal=read(D/"forecast-seal.json");assert seal["rows"]==sha(D/"forecasts.json.gz")
    out=read(D/"forecasts.json.gz");audit={}
    for _,issue,dup,trace in sources():
        if dup:continue
        for at,(_,args,obs) in enumerate(trace["events"]):
            k=h(issue+"|"+str(at))
            if k not in out:continue
            z=out[k];path=path_of(args);assert z["path"]==h(path)
            receipt=lines(obs);future={};conflict=set();views=0
            for tool,a,s in trace["events"][at+1:]:
                cmd=a.get("command")
                if tool=="other" or cmd not in ("view","str_replace","insert","create","undo_edit"):break
                if path_of(a)!=path:continue
                if cmd!="view":break
                for n,txt in lines(s).items():
                    views+=1
                    if n in future and future[n]!=txt:conflict.add(n)
                    future[n]=txt
            per={}
            for mode,m in z["maps"].items():
                pred=dict(m);assert len(m)==len(pred)
                stats={}
                for name,v in (("receipt",receipt),("future",future)):
                    intersect=set(pred)&set(v)
                    stats[name]=[len(intersect),sum(pred[i]!=h(v[i]) or (name=="future" and i in conflict) for i in intersect)]
                per[mode]=stats
            audit[k]=dict(views_lines=views,per=per)
    assert set(audit)==set(out)
    save("audit.json.gz",audit)
    def summarize(keys):
        if not keys:return {}
        issues=sorted({out[k]["issue"] for k in keys})
        idx={q:i for i,q in enumerate(issues)};v=np.zeros((len(issues),5))
        totals={m:Counter() for m in ("file","range","edges","local")};wins=losses=0
        for k in keys:
            z=out[k];i=idx[z["issue"]];v[i,0]+=1
            for j,m in enumerate(totals,1):
                same=z["sel"][m]==z["old"];v[i,j]+=same;t=totals[m];t["same"]+=same
                for yy,(checks,errors) in audit[k]["per"][m].items():t[yy+"_checks"]+=checks;t[yy+"_errors"]+=errors
            a=z["sel"]["local"]==z["old"];b=z["sel"]["range"]==z["old"];wins+=int(a and not b);losses+=int(b and not a)
        diff=(v[:,4]-v[:,2])/v[:,0]
        boot=np.random.default_rng(424116).integers(len(issues),size=(10000,len(issues)))
        return dict(issues=len(issues),events=len(keys),anchored=sum(out[k]["anchored"] for k in keys),methods=totals,
           wins=wins,losses=losses,macro=diff.mean(),ci=np.quantile(diff[boot].mean(axis=1),[.025,.975]).tolist())
    first={}
    for k,z in out.items():
        q=z["issue"]
        if q not in first or z["at"]<out[first[q]]["at"]:first[q]=k
    panels={"all":list(out),"localized":[k for k,z in out.items() if z["anchored"]],"first":list(first.values())}
    for field in ("panel","repo"):
        for name in set(z[field] for z in out.values()):panels[name]=[k for k,z in out.items() if z[field]==name]
    result={name:summarize(keys) for name,keys in panels.items()};save("results.json",result)
    print(result["all"])
if __name__=="__main__":
    if sys.argv[1]=="predict":forecast()
    elif sys.argv[1]=="grade":grade()


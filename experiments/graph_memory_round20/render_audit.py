"""Re-tokenize literal evidence, trim actual outputs, then audit exact source spans."""
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict,Counter
import os
import sys
from pathlib import Path
from statistics import mean
os.environ["RAYON_NUM_THREADS"]="1"
D=Path(__file__).resolve().parent; OLD=D.parent/"graph_memory_round19"
sys.path.insert(0,str(OLD/"tail_read"))
from tail import pilot,independent,load,compare,OFF
from assess import save
ARMS=("prefix","skip","ratio","prob","unprotected")
def shard(job):
    name,model,i=job;p=D/name;lock=load(p/f"{model}-forecast-seal.json");f=f"{model}-decisions-{i}.json.gz";assert pilot.sha(p/f)==lock["files"][f]
    tokenizer=pilot.Tokenizer.from_file("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json");assert tokenizer.truncation is None
    findings=[]
    for rr in load(p/f):
        t=rr["t"];raw=load(Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")/f"{i}-{t}.json.gz")
        fields=raw["fields"];nodes=rr["used"];ad=rr["addresses"]
        texts={k:fields[ad[e][0]][a:b] for k,(e,a,b,c) in nodes.items()}
        for q,arms in rr["picks"].items():
            out={}
            for arm in ARMS:
                take=arms[arm];snippets=[texts[k] for k in take];ctx="\n".join(snippets);encoded=tokenizer.encode(ctx,add_special_tokens=False)
                reported=sum(nodes[k][3] for k in take);real=len(encoded.ids);assert reported<=2048
                cut=len(ctx)
                if real>2048:
                    cut=encoded.offsets[2048][0]
                    while cut and len(tokenizer.encode(ctx[:cut],add_special_tokens=False).ids)>2048:cut-=1
                paid=real if real<=2048 else len(tokenizer.encode(ctx[:cut],add_special_tokens=False).ids)
                assert 0<=paid<=2048
                intervals=[];idx=0;visible=[]
                for k,s in zip(take,snippets,strict=True):
                    e,a,b,c=nodes[k];l=max(0,min(cut-idx,len(s)))
                    if l:
                        intervals.append([e,a,a+l]);visible.append(s[:l])
                    idx+=len(s)+1
                assert ctx[:cut].rstrip()==("\n".join(visible)).rstrip()
                out[arm]=[reported,real,paid,intervals]
            findings.append({"q":q,"t":t,"addr":ad,"picks":out})
    dst=p/f"{model}-render-{i}.json.gz";save(dst,findings);return pilot.sha(dst)
def forecast(name,model):
    p=D/name
    with ProcessPoolExecutor(3) as pool:sums=list(pool.map(shard,[(name,model,i) for i in range(8)]))
    save(p/f"{model}-render-seal.json",{"code":pilot.sha(D/"render_audit.py"),"plan":pilot.sha(D/"RENDER_PROTOCOL_RU.md"),"files":{f"{model}-render-{i}.json.gz":h for i,h in enumerate(sums)}})
def score(name,model):
    p=D/name;lock=load(p/f"{model}-render-seal.json")
    assert lock["plan"]==pilot.sha(D/"RENDER_PROTOCOL_RU.md") and lock["code"]==pilot.sha(D/"render_audit.py")
    original=load(p/f"{model}-outcomes.json.gz");gold=load(OFF/"gold-spans.json.gz")
    vals=defaultdict(dict);changed=Counter();over=Counter();maxcost=Counter();overlap=Counter()
    for f,h in lock["files"].items():
        assert pilot.sha(p/f)==h
        for row in load(p/f):
            q,t,ad=row["q"],row["t"],row["addr"]
            for arm,(nominal,real,paid,items) in row["picks"].items():
                spans=[{"event_id":ad[e][0],"json_pointer":ad[e][1],"char_start":a,"char_end":b} for e,a,b in items]
                coverage,density,full=independent(gold[q],[{"source_spans":[s]} for s in spans])
                f1=(2*density*coverage/(density+coverage)) if density+coverage else 0.
                vals[arm][q]={"t":t,"tokens":paid,"full_support":full,"coverage":coverage,"density":density,"f1":f1}
                before=original[arm][q];assert before["tokens"]==nominal and full<=before["full_support"] and coverage<=before["coverage"]+1e-12
                if real<=2048:assert abs(coverage-before["coverage"])<1e-12
                changed[arm]+=full!=before["full_support"];over[arm]+=real>2048;maxcost[arm]=max(maxcost[arm],real)
    assert all(set(v)==set(gold) for v in vals.values())
    stats={k:{"FS":mean(r["full_support"] for r in v.values()),"C":mean(r["coverage"] for r in v.values()),"render_overflows":over[k],
        "lost_full":changed[k],"max_raw_tokens":maxcost[k],"mean_paid":mean(r["tokens"] for r in v.values())} for k,v in vals.items()}
    strata={};pairs={}
    for k in ("ratio","prob","unprotected"):
        pairs[k+"-skip"]=compare(vals[k],vals["skip"])
        for typ in ("single","multiple"):
            ids=[q for q,g in gold.items() if (len({s["event_id"] for s in g})==1)==(typ=="single")]
            a,b=vals[k],vals["skip"]
            strata[k+"/"+typ]={"n":len(ids),"wins":sum(a[q]["full_support"]>b[q]["full_support"] for q in ids),
                "losses":sum(a[q]["full_support"]<b[q]["full_support"] for q in ids),"coverage_delta":mean(a[q]["coverage"]-b[q]["coverage"] for q in ids)}
    save(p/f"{model}-render-results.json",{"summary":stats,"strata":strata,"pairs":pairs})
    save(p/f"{model}-render-outcomes.json.gz",vals);print(name,model,stats,flush=True)
if __name__=="__main__":
    action,name,model=sys.argv[1:];{"predict":forecast,"score":score}[action](name,model)

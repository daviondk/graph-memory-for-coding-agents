"""Read the remaining token budget after the common, full-sized execution-provenance core."""
import bisect
import collections
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

D=Path(__file__).resolve().parent;R18=D.parents[1]/"graph_memory_round18"
E5=R18/"isetrace_e5";FT=D.parent/"trained_rank";OW=D.parent/"online_write";OFF=R18/"isetrace_official"
sys.path.insert(0,str(OW));import predict
sys.path.insert(0,str(E5));from project import pilot
from evaluate import compare
from verify_records import metrics as independent
from statistics import mean
def load(p):
    if isinstance(p,str):p=D/p
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def stable(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def put(p,v):
    if isinstance(p,str):p=D/p
    b=stable(v)+b"\n"
    if p.suffix==".gz":b=gzip.compress(b,mtime=0)
    if p.exists():assert p.read_bytes()==b,p
    else:p.write_bytes(b)
def lock():
    prior={folder.name+"/"+f:pilot.sha(folder/f) for folder,files in ((E5,("forecast-seal.json","inventory.json")),(OW,("forecast-lock.json","predict.py")),(OFF,("cohort.json",))) for f in files}
    put("design-lock.json",{"protocol":pilot.sha(D/"PROTOCOL_RU.md"),"code":pilot.sha(D/"tail.py"),"prior":prior,"models":["frozen","trained"]})
def source(model):
    assert model in ("frozen","trained");return E5 if model=="frozen" else FT
def source_seal(model):
    s=load("design-lock.json");assert s["protocol"]==pilot.sha(D/"PROTOCOL_RU.md") and s["code"]==pilot.sha(D/"tail.py")
    for f,h in s["prior"].items():
        name,rel=f.split("/");d={E5.name:E5,OW.name:OW,OFF.name:OFF}[name]
        assert pilot.sha(d/rel)==h
    driver=load(OW/"forecast-lock.json");src=source(model);model_info=load(src/"forecast-seal.json")
    ranks={f:sha for f,sha in model_info["forecasts"].items() if f.startswith("forecasts-main-")}
    assert len(ranks)==8 and len(driver["forecasts"])==8
    for f,h in ranks.items():assert pilot.sha(src/f)==h
    # Ensure raw text and metadata come from the exact same trajectory projection used for write policies.
    d=hashlib.sha256();files=sorted(predict.CACHE.glob("*.json.gz"))
    for file in files:d.update(file.name.encode()+b"\0"+bytes.fromhex(pilot.sha(file)))
    assert len(files)==1207 and d.hexdigest()==driver["projection"]==load(E5/"inventory.json")["projection_digest"]
    put(model+"-source.json",{"model_seal":pilot.sha(src/"forecast-seal.json"),"ranks":ranks,"blocks":driver["forecasts"],"private_projection":d.hexdigest(),"design":pilot.sha(D/"design-lock.json")})
def units(raw,r,rr):
    eindex={(eid,ptr):j for j,(eid,ptr) in enumerate(r["addresses"])}
    nodes={n["node_id"]:n for n in rr};shape={};by_event=collections.defaultdict(list)
    for k,n in nodes.items():
        assert len(n["source_spans"])==1
        s=n["source_spans"][0];e=eindex[s["event_id"],s["json_pointer"]]
        shape[k]=(e,s["char_start"],s["char_end"],n["token_count"]);by_event[e].append((s["char_start"],s["char_end"],k))
    flist=r["blocks"]
    parents=[]
    for e,a,b,c,nb in flist:parents.append([k for start,end,k in by_event[e] if start<=a and b<=end])
    return shape,parents
def plan_one(rec,shape,parents,blocks,meta,bm,question):
    rank=[n["node_id"] for n in rec["rr"]];place={k:i+1 for i,k in enumerate(rank)}
    prefix=rec["arms"]["prefix"];assert prefix==rank[:len(prefix)]
    remaining=2048-sum(shape[k][3] for k in prefix)
    pairs={(meta[k]["call_id"],meta[k]["node_kind"]) for k in prefix if meta[k].get("call_id")}
    other={"content.tool_output":"content.tool_argument","content.tool_argument":"content.tool_output"}
    def linked(k):
        m=meta[k];return (m.get("call_id"),other.get(m.get("node_kind"))) in pairs
    tail=rank[len(prefix):]
    core=list(prefix)
    for k in tail:
        if linked(k) and shape[k][3]<=remaining:core.append(k);remaining-=shape[k][3]
    ref=list(core);left=remaining
    for k in tail:
        if not linked(k) and shape[k][3]<=left:ref.append(k);left-=shape[k][3]
    assert ref==rec["arms"]["related"]
    used=collections.defaultdict(list)
    for k in core:
        e,a,b,_=shape[k];used[e].append((a,b))
    eligible={}
    for j,(e,a,b,c,_) in enumerate(blocks):
        if parents[j] and c<=remaining and all(not(a<y and x<b) for x,y in used[e]):
            eligible[j]=min(place[k] for k in parents[j])
    scores=bm.get_scores(predict.content_tokens(question)) if bm else [0]*len(blocks)
    by_lex=sorted(range(len(blocks)),key=lambda j:(-scores[j],j));lex_place={k:i+1 for i,k in enumerate(by_lex)}
    def choose(method):
        if method=="a":order=sorted(eligible,key=lambda j:(eligible[j],j))
        elif method=="b":order=sorted(eligible,key=lambda j:(eligible[j],-scores[j],j))
        else:order=sorted(eligible,key=lambda j:(-(1/(60+eligible[j])+1/(60+lex_place[j])),j))
        keep=[];available=remaining
        for j in order:
            cost=blocks[j][3]
            if cost<=available:keep.append(j);available-=cost
        return keep
    return {"prefix":prefix,"related":ref,"core":core,"fine":{method:choose(method) for method in ("a","b","c")},"remaining":remaining}
def shard(job):
    model,i=job;seal=load(model+"-source.json");name=f"forecasts-main-{i}.json.gz";bname=f"forecast-{i}.jsonl.gz"
    assert pilot.sha(source(model)/name)==seal["ranks"][name] and pilot.sha(OW/bname)==seal["blocks"][bname]
    by=collections.defaultdict(list)
    for q in load(source(model)/name):by[q["t"]].append(q)
    out=[];total=0
    with gzip.open(OW/bname,"rb") as f:
        for line in f:
            r=json.loads(line);t=r["t"];qs=by.pop(t)
            raw=load(predict.CACHE/f"{i}-{t}.json.gz");assert raw["t"]==t
            meta={v["item_id"]:v["metadata"] for v in raw["pool"]};question=dict(raw["q"])
            shape,parents=units(raw,r,qs[0]["rr"]);blocks=r["blocks"];addresses=r["addresses"]
            lex=[predict.content_tokens(raw["fields"][addresses[e][0]][a:b]) for e,a,b,_,_ in blocks]
            bm=predict.BM25Okapi(lex) if any(lex) else None
            rows={};needed=set();fine=set()
            for rec in qs:
                assert {a["node_id"] for a in rec["rr"]}==set(shape)
                selections=plan_one(rec,shape,parents,blocks,meta,bm,question[rec["q"]]);rows[rec["q"]]=selections
                needed.update(selections["core"]+selections["related"]+selections["prefix"])
                for arr in selections["fine"].values():fine.update(arr)
            out.append({"t":t,"addresses":addresses,"nodes":{k:shape[k] for k in sorted(needed)},
                        "fine":{str(j):blocks[j][:4] for j in sorted(fine)},"q":rows,"n_blocks":len(blocks),
                        "without_parent":sum(not row for row in parents)})
            total+=len(qs)
    assert not by
    put(f"{model}-picks-{i}.json.gz",out);return total
def predict_model(model):
    source_seal(model)
    with ProcessPoolExecutor(4) as pool:ns=list(pool.map(shard,[(model,i) for i in range(8)]))
    assert sum(ns)==2000
    put(model+"-forecast-lock.json",{"source":pilot.sha(D/(model+"-source.json")),"predictions":{f.name:pilot.sha(f) for f in sorted(D.glob(model+"-picks-*.json.gz"))}})
    print(model,"sealed",ns,flush=True)
def score_model(model):
    seal=load(model+"-forecast-lock.json");assert pilot.sha(D/(model+"-source.json"))==seal["source"]
    truth=load(OFF/"gold-spans.json.gz");cohort={r["query_id"]:r["trajectory_id"] for r in load(OFF/"cohort.json")};rows={};aux=collections.Counter()
    for fn,digest in seal["predictions"].items():
        assert pilot.sha(D/fn)==digest
        for rec in load(fn):
            t=rec["t"];addr=rec["addresses"];aux["blocks"]+=rec["n_blocks"];aux["without_parent"]+=rec["without_parent"]
            def node(name,row):
                e,a,b,c=row;eid,ptr=addr[e];span=pilot.SourceSpan(event_id=eid,json_pointer=ptr,char_start=a,char_end=b)
                return pilot.RankedNodeRecord(node_id=name,score=0,token_count=c,source_spans=(span,))
            coarse={k:node(k,v) for k,v in rec["nodes"].items()};fine={int(k):node("fine/"+k,v) for k,v in rec["fine"].items()}
            for q,info in rec["q"].items():
                assert q not in rows and cohort[q]==t
                g=tuple(pilot.SourceSpan.model_validate(v) for v in truth[q]);out={}
                for pol in ("prefix","related","core","a","b","c"):
                    if pol in ("prefix","related","core"):selected=[coarse[k] for k in info[pol]]
                    else:selected=[coarse[k] for k in info["core"]]+[fine[k] for k in info["fine"][pol]]
                    cost=sum(n.token_count for n in selected);assert cost<=2048
                    value=pilot.span_metrics_under_token_budget(tuple(selected),g,2048)
                    check=independent(truth[q],[n.model_dump() for n in selected])
                    for x,k in zip(check,("coverage","density","full_support"),strict=True):assert abs(x-getattr(value,k))<1e-12
                    out[pol]={"t":t,"tokens":cost,**{k:getattr(value,k) for k in ("coverage","density","full_support","f1")}}
                rows[q]=out
    assert set(rows)==set(truth)
    put(model+"-outcomes.json.gz",rows)
    by_arm={pol:{q:r[pol] for q,r in rows.items()} for pol in ("prefix","related","core","a","b","c")}
    stats={pol:{"full":int(sum(v["full_support"] for v in by.values())),**{k:mean(v[k] for v in by.values()) for k in ("coverage","density","f1","tokens")}} for pol,by in by_arm.items()}
    pairs={a+"-"+b:compare(by_arm[a],by_arm[b]) for a,b in (("b","related"),("b","a"),("c","b"),("b","prefix"),("c","related"),("a","related"))}
    put(model+"-results.json",{"n":len(rows),"unique_trajectories":len(set(cohort.values())),"stats":stats,"pairs":pairs,"block_stats":dict(aux)})
    print(model,stats,flush=True)
if __name__=="__main__":
    if sys.argv[1]=="lock":lock()
    elif sys.argv[1]=="predict":predict_model(sys.argv[2])
    else:score_model(sys.argv[2])

"""Locked extra-80 evaluation, no training on the development set."""
from factor import D,ROOT,app,save,load,sha,np,shape,gmod,rank_x,lin
from collections import defaultdict
from statistics import mean
import sys
from pathlib import Path
from graph_memory.graphs.provenance.builder import _argument_chunk_node_id,_output_chunk_node_id
sys.path.insert(0,str(app.OLD/"tail_read"));from tail import pilot,independent,compare
SRC=ROOT/"untuned_holdout";SPL=ROOT/"typed_reader/holdout80/source-plan.json"
def predict(co):
    orig=load(SRC/"forecast-seal.json");fp=SRC/"dense-ranks-extra80.json.gz";assert sha(fp)==orig["ranks"]
    src=load(SPL)["records"];by=defaultdict(list)
    for r in load(fp):by[r["t"]].append(r)
    out=[];mods=load(D/(co+"-weights.json"));pri=load(D/"prior.json")["models"]
    for t,qs in by.items():
        row=src[t];i=row["shard"];base=load(app.rd.DEV/f"{i}-{t}.json.gz")
        path=gmod.GRAPH/"graphs"/f"{i}-{t}.json.gz" if row["native"] else Path("D:/CodexResearch/x20-typed-reader-private")/(t+".json.gz")
        pool=[]
        for p in base["pool"]:
            meta=p["metadata"];k=(_argument_chunk_node_id if meta["node_kind"]=="content.tool_argument" else _output_chunk_node_id)(meta["call_id"],meta["chunk_index"])
            pool.append({**p,"item_id":k})
        keys,struct=shape(pool,gmod.project(t,{t:(path,row["sha"])}));at={k:j for j,k in enumerate(keys)}
        for r in qs:
            rr=r["rr"];ids=[n["node_id"] for n in rr];z=struct[[at[k] for k in ids]]
            x=rank_x(len(rr));signal=lin(mods["rank"],x);sp={"dense":-np.arange(len(rr)),"rank":signal}
            for name,field in (("factor","prior"),("degree","degree"),("shape","shape")):
                m=pri[field];sp[name]=signal+lin(m,z[:,m["columns"]])
            out.append({"q":r["q"],"t":t,"orders":{k:np.argsort(-v,kind="stable").tolist() for k,v in sp.items()}})
    assert len(out)==80 and len(by)==74
    fname=co+"-extra-ranks.json.gz";save(D/fname,out);save(D/(co+"-extra-seal.json"),{"file":sha(D/fname),"upstream":sha(fp),"weights":sha(D/(co+"-weights.json")),"prior":sha(D/"prior.json"),"plan":sha(D/"EXTERNAL_RU.md"),"code":sha(D/"external.py")})
def score(co):
    assert sha(D/(co+"-extra-ranks.json.gz"))==load(D/(co+"-extra-seal.json"))["file"]
    rr={q["q"]:q["rr"] for q in load(SRC/"dense-ranks-extra80.json.gz")};golds=load(app.OLD/"write_transfer/gold-spans.json.gz");cells=defaultdict(dict)
    for rec in load(D/(co+"-extra-ranks.json.gz")):
        q=rec["q"];nodes=[pilot.RankedNodeRecord.model_validate(r) for r in rr[q]];gold=tuple(pilot.SourceSpan.model_validate(s) for s in golds[q])
        for arm,rank in rec["orders"].items():
            for pol in ("prefix","skip"):
                take=[];left=2048
                for j in rank:
                    c=nodes[j].token_count
                    if c<=left:take.append(j);left-=c
                    elif pol=="prefix":break
                m=pilot.span_metrics_under_token_budget(tuple(nodes[j] for j in take),gold,2048)
                check=independent(golds[q],[rr[q][j] for j in take]);assert all(abs(v-getattr(m,k))<1e-12 for v,k in zip(check,("coverage","density","full_support"),strict=True))
                cells[pol+"/"+arm][q]={"t":rec["t"],"tokens":2048-left,**{k:getattr(m,k) for k in ("coverage","density","full_support","f1")}}
    vals={a:{"hits":sum(v["full_support"] for v in rs.values()),"coverage":mean(v["coverage"] for v in rs.values())} for a,rs in cells.items()}
    pairs={a:compare(rs,cells[a.split("/")[0]+"/dense"]) for a,rs in cells.items() if not a.endswith("/dense")}
    save(D/(co+"-extra-results.json"),{"n":80,"summary":vals,"pairs":pairs});save(D/(co+"-extra-outcomes.json.gz"),cells)
if __name__=="__main__":{"predict":predict,"score":score}[sys.argv[1]](sys.argv[2])

"""Independent source reconstruction. Does not import the generator or its factor construction."""
import os
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[k]="1"
from pathlib import Path
import sys,hashlib,json,gzip,math,collections,re
D=Path(__file__).resolve().parent;W=D.parents[1];R33=W/"graph_memory_round33";B=R33/"budget_loss";R19=W/"graph_memory_round19/trained_rank";P=W/"graph_memory_round22/prefix_read"
sys.path.insert(0,str(P))
from forecast import geometry,edges_by_name,ref
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def addr(v):return [h(v["event_id"]+"\0"+v["json_pointer"])[:16],v["char_start"],v["char_end"]]
def same(x,y):assert len(x)==len(y) and all(abs(a-b)<1e-10 for a,b in zip(x,y)),(x,y)
def merge(spans):
    result=collections.defaultdict(list)
    for k,l,r in sorted(spans):
        v=result[k]
        if v and l<=v[-1][1]:v[-1][1]=max(r,v[-1][1])
        else:v.append([l,r])
    return result
def length(v):return sum(b-a for k,z in v.items() for a,b in z)
def main():
    lock=read(D/"source.json");assert lock["output"]==sha(D/"index.html") and all(sha(W/k)==v for k,v in lock["source_sha"].items())
    embedded=json.loads(re.search(r'<script type="application/json" id="dataset">(.*?)</script>',(D/"index.html").read_text(encoding="utf8"),re.S)[1])
    out=read(B/"test-outcomes.json.gz");gr=read(B/"test-ranks.json.gz");groups=collections.defaultdict(list);wins=loss=both=zero=0
    for q,r in out.items():
        v=r["arms"];a=v["cost_worst_0.03"][0];b=v["frozen"][0]
        kind=("both" if b else "win") if a else ("loss" if b else "neither");groups[kind].append(q)
    ids=[q for k in ("win","loss","both","neither") for q in sorted(groups[k],key=lambda q:h("R34-reader-demo-v1|"+q))[:2]]
    assert [c["q"] for c in embedded["cases"]]==ids and embedded["population"]==len(out)==2000
    assert {k:len(v) for k,v in groups.items()}==embedded["counts"]=={"win":33,"loss":15,"both":1579,"neither":373}
    assert embedded["factorWins"]==1612 and embedded["graphWins"]==1594
    gg=read(R33/"relative_structure/weights.json")["models"]["global_role"];sm=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"];cm=read(B/"models.json")["models"]["cost_worst_0.03"]
    ggcoef=gg["coef"];gold=read(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz");graph_index=ref.graph_index();byq={}
    for i in range(8):
        for v in read(R19/f"forecasts-main-{i}.json.gz"):
            if v["q"] in ids:byq[v["q"]]=i,v
    oracle={};nrows=0;ne=0
    for case in embedded["cases"]:
        q=case["q"];i,base=byq[q];t=case["t"];assert base["t"]==t and q in groups[case["kind"]]
        gp,sign=graph_index[t];assert sha(gp)==case["graphSHA"]==sign
        src=Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")/f"{i}-{t}.json.gz";assert sha(src)==case["projectionSHA"]
        pool={v["item_id"]:v for v in read(src)["pool"]};fields=collections.Counter(v["source_spans"][0]["event_id"] for v in pool.values())
        gr_ids,pg=geometry(read(gp));edges=edges_by_name(gr_ids,pg);degs={k:[0]*8 for k in pool};ne+=len(edges)
        for a,b,z in edges:degs[a][2*z]+=1;degs[b][2*z+1]+=1
        roles={k:int(v["metadata"]["node_kind"]=="content.tool_output") for k,v in pool.items()}
        counts=collections.defaultdict(collections.Counter)
        for k,ch in degs.items():
            for z,x in enumerate(ch):counts[roles[k],z][x]+=1
        rr=base["rr"];n=len(rr);scores={k:[] for k in ("budget","graph","shape","dense")};real=[RankedNodeRecord.model_validate(v) for v in rr]
        ends=tuple(SourceSpan.model_validate(v) for v in gold[q]);assert [addr(v) for v in gold[q]]==case["gold"]
        for j,(r,node) in enumerate(zip(rr,case["nodes"],strict=True)):
            k=r["node_id"];cnt=j+1;ch=degs[k];role=roles[k];meta=pool[k]["metadata"];length_=r["token_count"];x=meta["chunk_index"];num=fields[pool[k]["source_spans"][0]["event_id"]]
            assert node["id"]==h(k)[:10] and node["s"]==[addr(y) for y in r["source_spans"]] and node["cost"]==length_ and node["cos"]==r["score"] and node["degrees"]==ch
            assert (role,x,num)==(node["role"],node["chunk"],node["group"])
            rel=[]
            for z,d in enumerate(ch):
                weights=counts[role,z];rel.append((sum(c for u,c in weights.items() if u<d)+weights[d]*.5)/sum(weights.values())-.5)
            raw=[role,math.log1p(length_),math.log1p(x),x/max(1,num-1),int(x==0),int(x==num-1),math.log1p(num)]
            shape=[a*b for a,b in zip(raw,ggcoef[:7])];absolute=[a*math.log1p(b) for a,b in zip(ggcoef[7:15],ch)];perc=[a*b for a,b in zip(ggcoef[15:],rel)]
            cost=[(a-c)/s*w for a,c,s,w in zip([math.log1p(cnt),math.log1p(length_),role,role*math.log1p(length_)],cm["center"],cm["scale"],cm["weights"])]
            rnk=sm["intercept"]+sum(a*b for a,b in zip(sm["coef"],[-math.log(cnt),1/cnt,(n-cnt)/max(n-1,1)]));grp=[rnk,gg["intercept"]+sum(shape),sum(absolute),sum(perc),sum(cost)]
            for field,values in (("shapeTerms",shape),("absTerms",absolute),("relTerms",perc),("costTerms",cost),("rel",rel),("p",grp)):same(node[field],values)
            for m,sc in (("dense",r["score"]),("budget",sum(grp)),("graph",sum(grp[:4])),("shape",sum(grp[:2]))):scores[m].append(sc)
        ggspan=merge(case["gold"]);total=length(ggspan);oracle[q]={};nrows+=n
        for m,values in scores.items():
            order=list(range(n)) if m=="dense" else sorted(range(n),key=lambda j:-values[j])
            if m in ("budget","graph"):assert gr[q]["cost_worst_0.03" if m=="budget" else "frozen"]==order
            vals={};native_order=tuple(real[j] for j in order)
            for budget in (128,255,512,999,1024,2047,2048,2049,3072,4096):
                used=0;take=[]
                for j in order:
                    if used+rr[j]["token_count"]>budget:break
                    used+=rr[j]["token_count"];take.append(j)
                spans=merge([addr(s) for j in take for s in rr[j]["source_spans"]])
                got=sum(max(0,min(b,v)-max(a,u)) for key,seg in ggspan.items() for a,b in seg for u,v in spans.get(key,[]))
                metrics=span_metrics_under_token_budget(native_order,ends,budget)
                assert abs(metrics.coverage-got/total)<1e-12 and metrics.full_support==float(got==total)
                vals[budget]={"used":used,"stop":len(take),"got":got,"total":total,"full":got==total}
            oracle[q][m]={"budgets":vals,"orderSHA":h(",".join(map(str,order)))}
    outpath=D/"ui-oracle.json";outpath.write_text(json.dumps(oracle,separators=(",",":"),sort_keys=True)+"\n",encoding="utf8")
    result=dict(cases=len(ids),candidates=nrows,directed_edges=ne,oracle_states=320,source=sha(D/"source.json"),oracle=sha(outpath),code=sha(Path(__file__)),cohort=embedded["counts"])
    (D/"verification.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf8");print(result)
if __name__=="__main__":main()
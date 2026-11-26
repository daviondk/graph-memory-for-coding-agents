"""Build a standalone numeric explainer from the selected, unchanged seed-13 study."""
import os
for env in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[env]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
from pathlib import Path
import sys,json,hashlib
from collections import defaultdict,Counter
D=Path(__file__).resolve().parent;W=D.parents[1];B=W/"graph_memory_round33/budget_loss";REL=B.parent/"relative_structure"
sys.path.insert(0,str(B));from data import f,load,sha,np,nm,OLD,R19,relative
TAG="R34-reader-demo-v1|"
RULES=["win","loss","both","neither"];CLASSES={(1,0):"win",(0,1):"loss",(1,1):"both",(0,0):"neither"}
def compact(x):return json.dumps(x,ensure_ascii=False,separators=(",",":"),allow_nan=False)
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def addr(s):return digest(s["event_id"]+"\0"+s["json_pointer"])[:16]
def span(s):return [addr(s),s["char_start"],s["char_end"]]
def main():
    receipts={};manifest=load(B/"manifest.json")
    def pinned(p):
        if p.parent==B:assert sha(p)==manifest[p.name]
        receipts[p.relative_to(W).as_posix()]=sha(p);return load(p)
    outcomes=pinned(B/"test-outcomes.json.gz")
    ranks=pinned(B/"test-ranks.json.gz");bm=pinned(B/"models.json")["models"]["cost_worst_0.03"];assert pinned(B/"selection.json")["policy"]=="cost_worst_0.03"
    gm=pinned(REL/"weights.json")["models"]["global_role"];sm=pinned(OLD/"hash64-weights.json")["rank"]
    gold=pinned(nm.OFF/"gold-spans.json.gz");summ=pinned(B/"transfer-results.json")
    by=defaultdict(list)
    for q,r in outcomes.items():
        a=r["arms"]["cost_worst_0.03"][0];b=r["arms"]["frozen"][0];by[CLASSES[int(a),int(b)]].append(q)
    wanted={q:cl for cl in RULES for q in sorted(by[cl],key=lambda q:digest(TAG+q))[:2]}
    assert len(outcomes)==2000 and len(wanted)==8
    idx=f.gmod.graph_index();records={};co=np.array(gm["coef"])
    for i in range(8):
        parents=pinned(R19/f"trained_rank/forecasts-main-{i}.json.gz")
        for r in parents:
            q=r["q"]
            if q not in wanted:continue
            t=r["t"];src=f.app.rd.stream.CACHE/f"{i}-{t}.json.gz";project=load(src);pool=project["pool"]
            ids,geom=f.shape(pool,f.gmod.project(t,idx));index={k:j for j,k in enumerate(ids)}
            rel=relative(geom,True);rr=r["rr"];rankfeat=f.rank_x(len(rr));dense=f.lin(sm,rankfeat);us=[];goldsp=[span(v) for v in gold[q]]
            for j,v in enumerate(rr):
                k=index[v["node_id"]];xx=geom[k]
                cost=v["token_count"];role=int(xx[0])
                assert int(round(np.expm1(xx[1])))==cost
                cx=np.array([np.log1p(j+1),np.log1p(cost),role,role*np.log1p(cost)])
                shape_terms=[float(a*b) for a,b in zip(xx[:7],co[:7])]
                abs_terms=(xx[7:]*co[7:15]).tolist();rel_terms=(rel[k]*co[15:]).tolist()
                corr=((cx-np.array(bm["center"]))/bm["scale"])*bm["weights"]
                parts=[float(dense[j]),float(gm["intercept"]+sum(shape_terms)),float(sum(abs_terms)),float(sum(rel_terms)),float(corr.sum())]
                rawsp=[span(z) for z in v["source_spans"]]
                us.append({"id":digest(v["node_id"])[:10],"role":role,"cost":cost,"cos":v["score"],"s":rawsp,"p":parts,
                         "degrees":np.rint(np.expm1(xx[7:])).astype(int).tolist(),"rel":rel[k].tolist(),"absTerms":abs_terms,"relTerms":rel_terms,
                         "shapeTerms":shape_terms,"costTerms":corr.tolist(),"chunk":int(round(np.expm1(xx[2]))),"group":int(round(np.expm1(xx[6])))})
            scores=np.asarray([n["p"] for n in us])
            for mode,jstop,model in [("budget",5,"cost_worst_0.03"),("graph",4,"frozen")]:
                assert np.argsort(-scores[:,:jstop].sum(axis=1),kind="stable").tolist()==ranks[q][model]
            assert len({u["id"] for u in us})==len(us)
            records[q]=dict(q=q,t=t,kind=wanted[q],gold=goldsp,nodes=us,intercept=gm["intercept"],
                  projectionSHA=sha(src),graphSHA=idx[t][1])
    assert records.keys()==wanted.keys()
    payload=dict(cases=[records[q] for q in wanted],counts={k:len(by[k]) for k in RULES},population=len(outcomes),
                 factorWins=sum(v["arms"]["cost_worst_0.03"][0] for v in outcomes.values()),graphWins=sum(v["arms"]["frozen"][0] for v in outcomes.values()),seed=13)
    text=(D/"template.html").read_text(encoding="utf8").replace("__EMBEDDED__",compact(payload).replace("<","\\u003c"))
    (D/"index.html").write_text(text,encoding="utf8",newline="\n")
    meta={"output":sha(D/"index.html"),"template":sha(D/"template.html"),"generator":sha(D/"build_demo.py"),"source_sha":receipts,"selection":TAG,"cases":list(wanted)}
    (D/"source.json").write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n",encoding="utf8")
    print({k:(len(by[k]),[len(v["nodes"]) for v in payload["cases"] if v["kind"]==k]) for k in RULES})
if __name__=="__main__":main()
from collections import Counter,defaultdict
from statistics import mean
import os,sys,runpy
os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
import numpy as np
from shared25 import *
from dataset import c,ro
def targets(name,picks):
    if name=="ise":
        reg=ro(R/"read_causes/registry.sqlite");gold=read(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
        mappings={}
        for r in picks.values():
            t=r["t"]
            if t not in mappings:mappings[t]={(eid,ptr):e for e,eid,ptr in reg.execute("select e,eid,ptr from address where t=?",(t,))}
        reg.close();return {q:[[(mappings[r["t"]][o["event_id"],o["json_pointer"]],o["char_start"],o["char_end"]) for o in gold[q]]] for q,r in picks.items()}
    if name=="mdd":
        fn=runpy.run_path(str(R/"transfer/score.py"),run_name="doc_score")
        gt,issues=fn["labels"](c.get_views());assert not issues and set(gt)==set(picks)
        return {q:[z[0]] for q,z in gt.items()}
    gt={}
    for art in read(SQUAD)["data"]:
        off=0
        for para in art["paragraphs"]:
            for row in para["qas"]:
                q=row["id"]
                if q not in picks:continue
                assert picks[q]["t"]==art["title"];answers=set()
                for a in row["answers"]:
                    l=a["answer_start"];h=l+len(a["text"])
                    assert para["context"][l:h]==a["text"]
                    answers.add((0,off+l,off+h))
                assert answers;gt[q]=[[x] for x in sorted(answers)]
            off+=len(para["context"])+2
    assert set(gt)==set(picks);return gt
def spans(raw):
    out=[]
    for e,l,h in sorted(raw):
        if h<=l:continue
        if out and out[-1][0]==e and l<=out[-1][2]:out[-1][2]=max(out[-1][2],h)
        else:out.append([e,l,h])
    return out
def overlap(a,b):return sum(max(0,min(h,u)-max(l,z)) for e,l,h in a for f,z,u in b if e==f)
def length(rs):return sum(h-l for e,l,h in rs)
def trial(visible,op,goals):
    new=spans(visible+[v[:3] for v in op]);extra=length(new)-length(visible)
    cov=max(overlap(new,g)/length(g) for g in goals);tokens=sum(v[3] for v in op)
    return {"fs":int(cov==1),"coverage":cov,"tokens":tokens,"headers":sum(v[6] for v in op),"issued":int(bool(op)),"two_headers":int(len(op)==2),"zero":int(bool(op) and extra==0),"chars":extra}
def inference(rows):
    names=[x+"-"+y for x,y in PAIRS]+["equal/"+x+"-"+y for x,y in PAIRS]
    groups=defaultdict(list)
    for r in rows:groups[r["t"]].append([r["diff"][k] for k in names])
    sizes=np.array([len(groups[t]) for t in sorted(groups)]);sums=np.array([np.sum(groups[t],axis=0) for t in sorted(groups)])
    n=len(rows);ng=len(groups);avg=sums.sum(axis=0)/n;z=sums-sizes[:,None]*avg
    se=np.sqrt((z**2).sum(axis=0)*ng/(ng-1))/n;rng=np.random.default_rng(250451);boot=[];mx=[]
    for _ in range(200):
        ix=rng.integers(0,ng,(50,ng));boot.extend(sums[ix].sum(axis=1)/sizes[ix].sum(axis=1)[:,None])
        signs=rng.choice([-1,1],(50,ng));mx.extend(np.max(np.abs(signs@z[:,:2]/n/np.where(se[:2]>0,se[:2],1)),axis=1))
    lo,hi=np.quantile(boot,[.025,.975],axis=0);cut=np.quantile(mx,.95);out={}
    for j,k in enumerate(names):
        vec=[r["diff"][k] for r in rows];active=[int(a) for a in sums[:,j] if a]
        a={"change_pp":100*avg[j],"interval_pp":[100*lo[j],100*hi[j]],"wins":vec.count(1),"losses":vec.count(-1),"nonzero_clusters":len(active)}
        if j<2:a["simultaneous_pp"]=[100*(avg[j]-cut*se[j]),100*(avg[j]+cut*se[j])]
        if len(active)<=20:
            mass=Counter({0:1})
            for v in active:
                tmp=Counter()
                for s,total in mass.items():tmp[s+abs(v)]+=total;tmp[s-abs(v)]+=total
                mass=tmp
            a["exact_p"]=sum(total for s,total in mass.items() if abs(s)>=abs(sum(active)))/2**len(active)
        out[k]=a
    return out
def summary(rows):
    out={}
    for k in ARMS:
        z=[r["arms"][k] for r in rows]
        out[k]={f:sum(v[f] for v in z) for f in ("fs","issued","two_headers","zero")}
        out[k].update({f:mean(v[f] for v in z) for f in ("coverage","tokens","chars","headers")})
    return out
def main(name):
    check();a=D/f"{name}-choices.json.gz";b=D/f"{name}-opened.json.gz"
    assert sha(a)==read(D/f"{name}-choice-seal.json")["actions"] and sha(b)==read(D/f"{name}-open-seal.json")["actions"]
    picks=read(a);ops=read(b);gt=targets(name,picks);rows=[]
    for q,r in sorted(picks.items()):
        cut=r["cut"];visible=spans(r["base"]);g=[spans(z) for z in gt[q]];old=trial(visible,[],g)
        vals={k:trial(visible,z,g) for k,z in ops[q]["arms"].items()}
        eq={k:[trial(visible,z,g) for z in pair] for k,pair in ops[q]["equal"].items()}
        assert all(u["tokens"]==v["tokens"] for u,v in eq.values()) and all(old["fs"]<=z["fs"] and z["tokens"]<=256 for z in vals.values())
        if cut:assert vals["adaptive"]==vals["left" if cut["left"] else "right"]
        diff={x+"-"+y:vals[x]["fs"]-vals[y]["fs"] for x,y in PAIRS}
        diff.update({"equal/"+k:v[0]["fs"]-v[1]["fs"] for k,v in eq.items()})
        rows.append({"q":q,"t":r["t"],"initial":old["fs"],"both_possible":bool(cut and cut["l"]>0),"left_chosen":bool(cut and cut["left"]),"has_component":bool(cut),
                     "oracle":max(vals[k]["fs"] for k in ("left","right","both")),"alternatives":len(g),"diff":diff,"arms":vals,"equal":eq})
    subset=[r for r in rows if r["both_possible"]];eqout={}
    for k in rows[0]["equal"]:
        z=[r["equal"][k] for r in rows];eqout[k]={"hits":[sum(p[j]["fs"] for p in z) for j in (0,1)],"tokens":mean(p[0]["tokens"] for p in z)}
    h=save(D/f"{name}-per-query.json.gz",rows)
    res={"n":len(rows),"clusters":len({r["t"] for r in rows}),"initial":sum(r["initial"] for r in rows),"has_component":sum(r["has_component"] for r in rows),
         "both_possible":len(subset),"selected_left":sum(r["left_chosen"] for r in rows),"complete_oracle":sum(r["oracle"] for r in rows),
         "multiple_alternatives":sum(r["alternatives"]>1 for r in rows),"methods":summary(rows),"both_possible_methods":summary(subset) if subset else {},"primary":inference(rows),"equal":eqout,"per_query":h}
    save(D/f"{name}-results.json",res);print(name,*[res[k] for k in ("n","clusters","initial","both_possible","selected_left","complete_oracle")]);print({k:z["fs"] for k,z in res["methods"].items()});print(res["primary"],res["equal"])
if __name__=="__main__":main(sys.argv[1])

"""Evaluate the next database action while retaining the initial context."""
from collections import Counter
from itertools import product
import runpy
import sqlite3
import numpy as np
from routes import D,S,c,read,write,sha

def test(values,groups):
    labels,idx=np.unique(groups,return_inverse=True)
    d=np.array(values);sums=np.bincount(idx,weights=d);cnt=np.bincount(idx)
    rng=np.random.default_rng(2401);boot=[]
    for _ in range(200):
        draw=rng.integers(len(cnt),size=(100,len(cnt)));boot.extend(sums[draw].sum(axis=1)/cnt[draw].sum(axis=1))
    eff=[int(x) for x in sums if x]
    obs=abs(sum(eff))
    if len(eff)<=18:
        p=sum(abs(sum(a*b for a,b in zip(bits,eff)))>=obs for bits in product((-1,1),repeat=len(eff)))/(2**len(eff))
    else:
        exceed=0
        for _ in range(100):
            z=rng.choice((-1,1),size=(1000,len(eff)))@eff;exceed+=int(sum(abs(z)>=obs))
        p=(exceed+1)/100001
    return {"delta":d.mean(),"n_clusters":len(cnt),"wins":int(sum(d>0)),"losses":int(sum(d<0)),
            "nonzero_clusters":len(eff),"ci_bonf":np.quantile(boot,[.00625,.99375]).tolist(),"p_signflip":p}
def main():
    seal=read(D/"action-lock.json")
    assert sha(D/"PROTOCOL_RU.md")==seal["plan"] and sha(D/"routes.py")==seal["code"]
    source=S/"transfer"
    sc=runpy.run_path(str(source/"score.py"),run_name="md_labels"); docs,_=sc["labels"](c.get_views());un=sc["union"];ov=sc["overlap"]
    off=D.parents[1]/"graph_memory_round18/isetrace_official";g=read(off/"gold-spans.json.gz")
    db=sqlite3.connect((S/"read_causes/registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    ids={(t,eid,ptr):e for t,e,eid,ptr in db.execute("select t,e,eid,ptr from address")};db.close()
    results={};primary=[];outputs={}
    for corpus in ("isetrace","multidoc"):
        path=D/f"actions-{corpus}.json.gz";assert sha(path)==seal["files"][path.name]
        stats={};rows={}
        for q,r in read(path).items():
            if corpus=="isetrace":
                group=r["t"];gt=[(ids[group,v["event_id"],v["json_pointer"]],v["char_start"],v["char_end"]) for v in g[q]]
            else:gt=docs[q][0];group=gt[0][0]
            gt=un(gt);den=sum(h-l for _,l,h in gt)
            base=un(r["base"]);orig=ov(gt,base);span=sum(h-l for _,l,h in base)
            val={}
            for a,p in r["actions"].items():
                ss=un(base+([p[:3]] if p and p[1]<p[2] else []))
                cov=ov(gt,ss);added=sum(h-l for _,l,h in ss)-span
                tokens=p[3] if p else 0
                assert orig<=cov<=den and added>=0 and tokens<=256
                v=[int(cov==den),cov/den,added,tokens,int(p is None),int(bool(p) and not added)]
                val[a]=v
                if a not in stats:stats[a]=[0.0]*6
                for k,item in enumerate(v):stats[a][k]+=item
            rows[q]={"g":group,"base":int(orig==den),"scores":val}
        N=len(rows)
        assert (N,int(stats["first_positive"][0]))==((2000,1697) if corpus=="isetrace" else (661,450))
        contrasts=[]
        order=[rows[q] for q in sorted(rows)]
        for control in ("same_window","first_positive"):
            p=test([v["scores"]["right_edge"][0]-v["scores"][control][0] for v in order],[v["g"] for v in order])
            p.update(corpus=corpus,control=control);contrasts.append(p);primary.append(p)
        results[corpus]={"n":N,"initial":sum(r["base"] for r in order),"contrasts":contrasts,
          "summary":{k:{"hits":int(v[0]),"coverage":v[1]/N,"added_chars":v[2]/N,"tokens":v[3]/N,"abstain":int(v[4]),"empty_reads":int(v[5])} for k,v in stats.items()},
          "unequal_matched_cost":sum(x["scores"]["right_edge_matched"][3]!=x["scores"]["first_positive_matched"][3] for x in order)}
        outputs[corpus]=rows
    peak=0
    for j,p in enumerate(sorted(primary,key=lambda x:x["p_signflip"])):
        peak=max(peak,min(1,(4-j)*p["p_signflip"]));p["holm_p"]=peak
    write(D/"per-query.json.gz",{"columns":["full_support","coverage","added_chars","tokens","abstain","empty_read"],"corpora":outputs})
    write(D/"results.json",{"results":results,"outcomes":sha(D/"per-query.json.gz"),"seal":sha(D/"action-lock.json")})
    for k,r in results.items():print(k,r["summary"],r["contrasts"])
if __name__=="__main__":main()

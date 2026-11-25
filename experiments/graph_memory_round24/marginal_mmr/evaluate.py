"""Score frozen opens and common realized-cost pairs from source spans."""
import os
os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
from collections import Counter,defaultdict
from statistics import mean,median
import importlib,sys
import numpy as np
from io24 import D,read,sha,save,PAIRS,check
def coalesce(triples):
    by=defaultdict(list)
    for e,l,h in triples:
        if l<h:by[e].append((l,h))
    result={}
    for e,ranges in by.items():
        done=[]
        for l,h in sorted(ranges):
            if done and done[-1][1]>=l:done[-1][1]=max(done[-1][1],h)
            else:done.append([l,h])
        result[e]=done
    return result
def total(v):return sum(h-l for a in v.values() for l,h in a)
def overlap(v,g):return sum(max(0,min(b,y)-max(a,x)) for e,sp in g.items() for a,b in sp for x,y in v.get(e,()))
def pairs_inference(rows):
    keys=[x+"-"+y for x,y in PAIRS]+["equal/"+x+"-"+y for x,y in PAIRS];group=defaultdict(list)
    for r in rows:group[r["t"]].append([r["contrasts"][k] for k in keys])
    sizes=np.array([len(group[t]) for t in sorted(group)]);sums=np.array([np.sum(group[t],axis=0) for t in sorted(group)])
    n=len(rows);g=len(sizes);d=sums.sum(axis=0)/n;ctr=sums-sizes[:,None]*d;se=np.sqrt(g/(g-1)*(ctr**2).sum(axis=0))/n
    rng=np.random.default_rng(242325);boot=[];tmax=[]
    for _ in range(200):
        ix=rng.integers(0,g,(50,g));boot.extend(sums[ix].sum(axis=1)/sizes[ix].sum(axis=1)[:,None])
        signs=rng.choice([-1,1],size=(50,g));blo=(signs@ctr[:,:2])/n
        tmax.extend(np.max(np.abs(blo/np.where(se[:2]!=0,se[:2],1)),axis=1))
    lower,upper=np.quantile(boot,[.025,.975],axis=0);cut=np.quantile(tmax,.95)
    result={}
    for i,k in enumerate(keys):
        v=np.array([r["contrasts"][k] for r in rows]);active=sums[:,i];active=active[active!=0]
        data={"n":n,"clusters":g,"wins":int((v>0).sum()),"losses":int((v<0).sum()),"delta_pp":float(100*d[i]),"cluster95_pp":[100*lower[i],100*upper[i]],"nonzero_clusters":len(active)}
        if i<2:data["simultaneous95_pp"]=[100*(d[i]-cut*se[i]),100*(d[i]+cut*se[i])]
        if len(active)<=20:
            null=Counter({0:1})
            for a in active:
                nxt=Counter()
                for s,count in null.items():nxt[s+abs(a)]+=count;nxt[s-abs(a)]+=count
                null=nxt
            data["two_sided_sign_flip"]=sum(count for s,count in null.items() if abs(s)>=abs(active.sum()))/2**len(active)
        result[k]=data
    return result

def main(name):
    check();s=read(D/f"{name}-open-seal.json");p=D/f"{name}-opened.json.gz";assert sha(p)==s["actions"]
    cs=read(D/f"{name}-choice-seal.json");a=D/f"{name}-choices.json.gz";assert sha(a)==cs["choices"] and sha(D/f"{name}-choice-seal.json")==s["choices"]
    choices=read(a);opened=read(p);targets=importlib.import_module(name).targets(choices)
    assert set(choices)==set(opened)==set(targets);rows=[];different=Counter();stats=defaultdict(list)
    for q in sorted(choices):
        r=choices[q];ops=opened[q];base=r["base"];prior=coalesce(base);g=coalesce(targets[q]);den=total(g);size=total(prior);old=overlap(prior,g)
        def score(op):
            if op:
                e,l,h,c=op;v=coalesce(base+[[e,l,h]])
                assert 0<c<=256 and any(f==e and a<=l<b for f,a,b in base)
            else:v=prior;c=0
            cov=overlap(v,g);new=total(v)-size
            assert cov>=old and new>=cov-old
            return {"fs":int(cov==den),"cov":cov/den,"new":new,"new_gold":cov-old,"tokens":c,"issued":int(op is not None),"zero_issued":int(op is not None and new==0)}
        vals={k:score(v) for k,v in ops["arms"].items()}
        eq={k:[score(x),score(y)] for k,(x,y) in ops["equal"].items()}
        assert all(x["tokens"]==y["tokens"] for x,y in eq.values())
        ctr={x+"-"+y:vals[x]["fs"]-vals[y]["fs"] for x,y in PAIRS}
        ctr.update({"equal/"+k:x["fs"]-y["fs"] for k,(x,y) in eq.items()})
        rows.append({"q":q,"t":r["t"],"base_fs":int(old==den),"values":vals,"equal":eq,"contrasts":ctr})
        u=r["stats"];different["windows"]+=u["n"];different["unequal_penalty"]+=u["different_penalties"];different["queries_unequal_penalty"]+=u["different_penalties"]>0
        for l in (25,50,75):
            x=r["picks"][f"max_{l}"];y=r["picks"][f"union_{l}"]
            different[f"different_choice_{l}"]+=x!=y
        for k in ("ranking_ns","geometry_headers_ns"):stats[k].append(u[k])
        for k,v in u["numeric_ns"].items():stats[k].append(v)
    n=len(rows);means={};equal={}
    for k in rows[0]["values"]:
        v=[r["values"][k] for r in rows]
        means[k]={f:mean(a[f] for a in v) for f in ("tokens","new","new_gold","cov")}
        means[k].update({f:sum(a[f] for a in v) for f in ("fs","issued","zero_issued")})
    for k in rows[0]["equal"]:
        v=[r["equal"][k] for r in rows]
        equal[k]={"hits":[sum(z[i]["fs"] for z in v) for i in (0,1)],"mean_tokens":mean(z[0]["tokens"] for z in v),"exact":sum(z[0]["tokens"]==z[1]["tokens"] for z in v)}
    h=save(D/f"{name}-per-query.json.gz",rows)
    res={"n":n,"base_fs":sum(r["base_fs"] for r in rows),"clusters":len({r["t"] for r in rows}),"methods":means,"pairs":pairs_inference(rows),"equal":equal,
         "geometry":different,"median_us":{k:median(v)/1000 for k,v in stats.items()},"per_query":h,"open_lock":sha(D/f"{name}-open-seal.json")}
    save(D/f"{name}-results.json",res);print(name,res["geometry"],res["pairs"],res["equal"])
if __name__=="__main__":main(sys.argv[1])

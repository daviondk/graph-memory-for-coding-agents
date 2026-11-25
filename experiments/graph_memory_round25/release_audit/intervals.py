import os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from collections import Counter,defaultdict
from qcheck import D,Q,rd,wr,close
def calc(rows,cseed,blocks,batch,checkp):
    groups=defaultdict(list)
    for group,x in rows:groups[group].append(x)
    ordered=sorted(groups);g=len(ordered);s=np.array([sum(groups[t]) for t in ordered]);n=np.array([len(groups[t]) for t in ordered])
    rng=np.random.default_rng(cseed);boot=[]
    for i in range(blocks):
        take=rng.integers(0,g,(batch,g));boot.extend(np.sum(s[take],axis=1)/np.sum(n[take],axis=1))
    ci=np.quantile(boot,[.00625,.99375]).tolist()
    if not checkp:return ci,None
    a=s[s!=0];obs=abs(sum(a))
    if len(a)<=18:
        cnt=Counter({0:1})
        for v in a:
            nextc=Counter()
            for t,f in cnt.items():nextc[t+v]+=f;nextc[t-v]+=f
            cnt=nextc
        prob=sum(f for t,f in cnt.items() if abs(t)>=obs)/2**len(a)
    else:
        hits=0
        for i in range(100):
            signs=rng.choice([-1,1],(1000,len(a)));hits+=(abs(signs@a)>=obs).sum()
        prob=float((hits+1)/100001)
    return ci,prob
def main():
    d=rd(Q/"decisions.json.gz");r=rd(Q/"results.json")["results"];qcount=0
    for tag,rr in r.items():
        for k,comp in rr["comparisons"].items():
            got,_=calc([(z["g"],z["arms"]["bloom_lazy"][3]-z["arms"][k][3]) for z in d if z["c"]==tag],2517,160,100,False)
            assert np.allclose(got,comp["cluster98_75"],rtol=0,atol=1e-9);qcount+=1
    S=D.parent/"sequential_open";qs=rd(S/"per-query.json.gz")["corpora"];res=rd(S/"results.json")["corpora"];n=0;raw=[]
    for ds,table in res.items():
        rows=qs[ds]
        for k,z in table["paired"].items():
            a,b=k.split(" vs ");ci,p=calc([(r["g"],r["steps"][a][0]-r["steps"][b][0]) for r in rows.values()],2401,200,100,True)
            assert np.allclose(ci,z["ci_bonf"],rtol=0,atol=1e-12) and close(p,z["p_signflip"]);n+=1
            if "holm_p" in z:raw.append((p,z["holm_p"]))
    running=0
    for j,(p,old) in enumerate(sorted(raw)):
        running=max(running,min(1,(len(raw)-j)*p));assert close(running,old)
    z={"query_byte_CI":qcount,"sequential_CI_and_signflip":n,"holm_family":len(raw)};wr(D/"statistics-checks.json",z);print(z)
if __name__=="__main__":main()

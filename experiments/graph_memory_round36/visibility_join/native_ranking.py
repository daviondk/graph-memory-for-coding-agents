"""Re-rank the identical visible dense order with degree columns supplied by physical SQLite."""
from common import *
import os,sys,tempfile
for k in ("MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
from sqlbench import reader,build,JOIND
sys.path.insert(0,str(W/"graph_memory_round34/live_reader"));import live as l
from scipy.stats import rankdata
np=l.np
def main():
    data=load(D/"input.json.gz");xs=load(D/"reader-checks.json.gz");ex=load(D/"extraction.json");assert ex["reader"]==sha(D/"reader-checks.json.gz") and ex["input"]==sha(D/"input.json.gz")
    graph,rank,_,patch,_=l.read_models();cnt={};which=set(load(D/"plan.json")["native_hids"])
    with tempfile.TemporaryDirectory(dir=D) as temp:
        main_db=reader(D/"grouped.sqlite3");extra={h:z for h,z in data.items() if int(h)>=128};path=Path(temp)/"extra.sqlite3";build(path,extra,"grouped");side=reader(path)
        for h,prs in xs.items():
            hid=int(h);db=main_db if hid<128 else side
            for i,p in enumerate(prs):
                chk=data[h]["checks"][i];kind=p["cut"];assert kind==chk["cut"]
                d=db.execute(JOIND,{"h":hid,"t":chk["at"]}).fetchall();assert hashobj(d)==chk["degrees"]
                by={u:[o,ii] for u,o,ii in d};nids=p["units"];x=np.array(p["x"]);role=x[:,0];cost=np.array(p["cost"]);deg=np.log1p(np.array([by.get(u,[0,0]) for u in nids]));x[:,11:13]=deg
                for r in (0,1):
                    a=np.flatnonzero(role==r)
                    if len(a):x[a,19:21]=(rankdata(deg[a],axis=0,method="average")-.5)/len(a)-.5
                prior=l.score(graph,x);n=len(x);rn=np.arange(1,n+1);sig=l.score(rank,np.column_stack((-np.log(rn),1/rn,(n-rn)/max(1,n-1))))
                for (avail,perm),expected in zip(p["q"],p["wanted"],strict=True):
                    aa=np.asarray(avail);pm=np.asarray(perm);c=cost[pm];v=role[pm];cor=l.correct(patch,np.column_stack((np.log1p(rn),np.log1p(c),v,v*np.log1p(c))));ordering=np.argsort(-(sig+prior[pm]+cor),kind="stable");ans=[aa[l.prefix(ordering,c,b)].tolist() for b in l.BUDGETS]
                    assert hashobj(ans)==expected,(hid,kind);scope="primary" if hid<128 else "extra"
                    cnt[scope]=cnt.get(scope,0)+1
        main_db.close();side.close()
    save(D/"ranking-audit.json",{"selections_checked":{m:k*3 for m,k in cnt.items()},"query_cuts":cnt,"budgets":list(l.BUDGETS),"model":"R33 cost_worst_0.03 / Dense-FT seed 13","norms":"within-role degree midranks","grouped_db":sha(D/"grouped.sqlite3"),"extraction":sha(D/"extraction.json"),"input":ex["input"],"script":sha(D/"native_ranking.py")});print(cnt)
if __name__=="__main__":main()

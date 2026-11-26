"""Use R42's independent numeric inputs at coincident cuts with online Dense tie handling."""
import os,sys
for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[k]="1"
from collections import defaultdict,Counter
from io43 import D,W,R41,R42,SEEDS,read,save,sha,signed
sys.path.insert(0,str(R42))
from models42 import inputs,portable,np
from core42 import firstfit


def main():
    names=("full","rich","cross","local","sham")
    lock=read(D/"forecast-seal.json");fit=signed(R42/"models.json")["models"]
    previous={};counts=defaultdict(Counter)
    for sh in range(8):
        tr=D/f"traces-{sh}.json.gz";packet=D/f"packets-{sh}.json.gz";assert [sha(packet),sha(tr)]==lock["outputs"][str(sh)]
        old={t:h for t,cut,j,n,e,h in read(R41/f"forecast-{sh}-seal.json")["traces"] if cut==50}
        equal={t for t,fire,k,c,n,events,nn,h in read(tr) if fire and old[t]==h}
        packets=read(packet)
        feats=R42/f"test-{sh}.npz";records=R42/f"test-{sh}.json.gz"
        assert [sha(records),sha(feats)]==read(R42/f"features-{sh}-seal.json")["rows"]["test"]
        with np.load(feats) as a:
            groups=[];indices=[];p=0
            for q,t,n,ids in read(records):
                if t in equal:
                    groups.append((q,t,n,np.array(ids)))
                    indices.extend(range(p,p+n))
                    assert ids==packets[q][2]
                p+=n
            if not groups:continue
            m,e,sham=(a[k][indices] for k in ("meta","edge","sham"))
            cost=np.rint(np.expm1(m[:,1])).astype(int)
            for s in SEEDS:
                sem=a[f"sem{s}"][indices].copy()
                pos=0
                for q,t,n,ids in groups:
                    sl=slice(pos,pos+n);pos+=n
                    order=np.argsort(-sem[sl,3],kind="stable");rank=np.empty(n);rank[order]=np.arange(1,n+1)
                    sem[sl,0]=np.log1p(rank);sem[sl,1]=1/rank;sem[sl,2]=(n-rank)/max(1,n-1)
                values={k:portable(fit[k]["hgb"],inputs(sem,m,e,sham,k)) for k in names}
                values["dense"]=-sem[:,0]
                pos=0
                for q,t,n,ids in groups:
                    sl=slice(pos,pos+n);pos+=n
                    for k,v in values.items():
                        idx=np.lexsort((sem[sl,0],-v[sl]))
                        restored=ids[firstfit(idx,cost[sl])].tolist()
                        published=packets[q][3][str(s)][k]
                        counts[k].update(total=1,ordered=int(published==restored),same_set=int(set(restored)==set(published)))
    save(D/"same-time-numeric.json",dict(counts=counts,seal=sha(D/"forecast-seal.json")))
    print(dict(counts))


if __name__=="__main__":main()

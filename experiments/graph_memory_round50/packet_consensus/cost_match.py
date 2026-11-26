"""Post-hoc equal-ceiling comparison, with both the rescaled and original mandatory prefix."""
import hashlib
from collections import defaultdict
from run import *
from grade_packets import STREAM,signed as study_data

REG = "0abf6fb4d4a8a61d57979888e9ebe83c2457983c9cc82fcbb3e5fe03d27cf5d8"

def forecast():
    assert sha(D/"BUDGET_CONTROL_RU.md")==REG
    src=read(signed("pool.json.gz"))
    ref=read(D/"packets.json.gz")
    assert sha(D/"packets.json.gz")==read(D/"forecast-seal.json")["forecasts"]
    ranks=[read(signed(f"ranks-{s}.json.gz")) for s in SEEDS]
    gain=[np.frombuffer(gzip.decompress(signed(f"utility-{s}.f64.gz").read_bytes()),dtype="<f8") for s in SEEDS]
    lib=Reader(False).lib
    fn=lib.solve
    fn.argtypes=[ct.c_int]*5+[ct.c_void_p]*8
    fn.restype=ct.c_int
    packets={}
    start=0
    for q,r in sorted(src.items()):
        cost=np.asarray(r["c"],dtype=np.int32)
        n=len(cost)
        u=np.mean([g[start:start+n] for g in gain],axis=0)
        start+=n
        cp_rows=[]
        for cp in range(2):
            denom=np.zeros(n)
            for rank in ranks:
                denom[rank[q][1+cp]]+=1/(60+np.arange(1,n+1))
            order=np.argsort(-denom,kind="stable").astype(np.int32)
            v=u[order]
            fixed=np.rint(v*2**32).astype(np.int64)
            end=np.array([n],dtype=np.int32)
            count=np.zeros(1,dtype=np.int32)
            out=np.empty(n,dtype=np.int32)
            stats=np.zeros(3,dtype=np.int64)
            budget=int(sum(cost[ref[q][1][cp]["hamming_dp"]]))
            one={"hamming":ref[q][1][cp]["hamming_dp"]}
            for name,b,t in [("mean_full",2048,1024),("mean_reduced",budget,budget//2),("mean_keep_head",budget,min(1024,budget))]:
                k=fn(n,1,b,t,0,end.ctypes.data,order.ctypes.data,cost.ctypes.data,fixed.ctypes.data,v.ctypes.data,
                     count.ctypes.data,out.ctypes.data,stats.ctypes.data)
                assert k>=0 and count[0]==k
                ids=out[:k].tolist()
                assert sum(cost[ids])<=b
                one[name]=ids
            assert one["mean_full"]==ref[q][1][cp]["mean_dp"]
            cp_rows.append(one)
        packets[q]=[r["t"],cp_rows]
    put(D/"budget-packets.json.gz",packets)
    put(D/"budget-seal.json",dict(protocol=REG,code=sha(Path(__file__)),forecasts=sha(D/"budget-packets.json.gz")))

def analysis():
    assert read(D/"budget-seal.json")["forecasts"]==sha(D/"budget-packets.json.gz")
    packets=read(D/"budget-packets.json.gz");costs=read(signed("pool.json.gz"))
    gold=study_data(STREAM,"judgments.json.gz")
    raw={}
    for q,(t,panels) in packets.items():
        goldq=gold[hashlib.sha256(q.encode()).hexdigest()]
        total=sum(w for w,_ in goldq)
        cp_scores=[]
        for preds in panels:
            scores={}
            for name,ids in preds.items():
                covered=sum(w for w,strong in goldq if set(ids).intersection(strong))
                scores[name]=[int(covered==total),covered/total,sum(costs[q]["c"][i] for i in ids)]
            cp_scores.append(scores)
        raw[q]=[t,cp_scores]
    put(D/"budget-outcomes.json.gz",raw)
    groups=sorted({t for t,_ in raw.values()});idx={t:i for i,t in enumerate(groups)}
    summary={}
    for cp in range(2):
        arms=["hamming","mean_full","mean_reduced","mean_keep_head"]
        x=np.zeros((len(idx),4,3));n=np.zeros(len(idx))
        for t,panels in raw.values():
            x[idx[t]]+=[panels[cp][a] for a in arms]
            n[idx[t]]+=1
        means=x.sum(axis=0)/n.sum();rng=np.random.default_rng(50086);blocks=[]
        for _ in range(100):
            w=rng.multinomial(len(idx),np.full(len(idx),1/len(idx)),size=100)
            blocks.append(((w@x.reshape(len(idx),-1))/(w@n)[:,None]).reshape(-1,4,3))
        boot=np.concatenate(blocks)
        comparisons={}
        for j,a in enumerate(arms):
            unit=[100,100,1]
            delta=(boot[:,0]-boot[:,j])*unit
            comparisons[a]=dict(effect=((means[0]-means[j])*unit).tolist(),ci=np.percentile(delta,[2.5,97.5],axis=0).T.tolist())
        summary[("recall","full_support")[cp]]=dict(means=dict(zip(arms,means.tolist())),versus=comparisons)
    put(D/"budget-results.json",summary)
    for cp,s in summary.items(): print(cp,s["versus"]["mean_reduced"],s["versus"]["mean_full"])
if __name__=="__main__":
    forecast()
    analysis()


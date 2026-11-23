"""Independent direct native DenseTaskRetriever on 8 hash-selected trajectories, CPU FP32."""
import hashlib,sys,time
from prepare import ROOT,RUN,pilot,load,put
from project import CACHE,reqs
from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever
def key(x):return hashlib.sha256(('R19-native-trained-direct|'+x).encode()).digest()
def selection():
    s=load(ROOT/'split.json.gz')['test'];ids=sorted({q['t'] for q in s},key=key)[:8]
    qs={t:min((r['q'] for r in s if r['t']==t),key=key) for t in ids}
    put(ROOT/'direct-plan.json',dict(study_sha256=pilot.sha(ROOT/'prediction-plan.json'),cpu_audit_code=pilot.sha(ROOT/'direct_audit.py'),queries_by_trajectory=qs,threads=4,fixed_count=8))
def rank():
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    plan=load(ROOT/'direct-plan.json');assert plan['cpu_audit_code']==pilot.sha(ROOT/'direct_audit.py')
    retr=DenseTaskRetriever(model_name=str(RUN/'model'),device='cpu');rows=[];start=time.monotonic()
    for t,q in sorted(plan['queries_by_trajectory'].items()):
        path,=(CACHE/'projection').glob('*-'+t+'.json.gz');r=next(r for r in reqs(load(path)) if r.task_id==q)
        pred=retr.rank(r)
        rows.append(dict(t=t,q=q,ranked=[n.model_dump() for n in pred]));print(q,len(pred),round(time.monotonic()-start,1),flush=True)
    put(ROOT/'direct-cpu.json.gz',rows);put(ROOT/'direct-cost.json',dict(queries=len(rows),candidates=sum(len(r['ranked']) for r in rows),seconds=time.monotonic()-start))
def evaluate():
    rows={r['q']:r for r in load(ROOT/'direct-cpu.json.gz')};checks=[];err=0.;tops=0
    seal=load(ROOT/'forecast-seal.json');assert all(pilot.sha(ROOT/n)==h for n,h in seal['forecasts'].items())
    for f in seal['forecasts']:
        for p in load(ROOT/f):
            q=p['q']
            if q not in rows:continue
            a=rows[q]['ranked'];b=p['rr'];aa=[r['node_id'] for r in a];bb=[r['node_id'] for r in b];assert set(aa)==set(bb)
            sc={r['node_id']:r['score'] for r in a}
            checks.append(dict(q=q,t=p['t'],n=len(a),top1=aa[:1]==bb[:1],top5_order=aa[:5]==bb[:5],all_order=aa==bb,max_abs=max(abs(sc[r['node_id']]-r['score']) for r in b)))
    assert len(checks)==len(rows)==8;put(ROOT/'direct-agreement.json',dict(rows=checks,totals={k:sum(r[k] for r in checks) for k in ['top1','top5_order','all_order']},max_abs=max(r['max_abs'] for r in checks)))
if __name__=='__main__':{'plan':selection,'rank':rank,'check':evaluate}[sys.argv[1]]()

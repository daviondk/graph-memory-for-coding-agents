"""Predict from observed events, seal all checkpoints, then score against future edits."""
import argparse, base64, collections, gzip, hashlib, json, os, platform, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from schema_codec import HERE,OLD,anchor,memory,prior,encode,decode,read,rows,save,sha
from shared import write
BUDGET=4096
ARMS=('legacy','generic','edges')
BEST=read(HERE/'dev.json')['best']
ALG={'legacy':'deflate3','generic':BEST,'edges':BEST}
LAYOUT={'legacy':'json','generic':'json','edges':'edges'}
def linecount(x):return sum(len(r[2]) for _,_,runs in x[2] for r in runs)
def predict(k):
    ws=anchor.weights();prior.advance=anchor.anchored_advance
    memory.unpack=lambda blob,_:decode(blob)
    with gzip.open(HERE/f'cuts_{k}.gz','wt',encoding='utf8',compresslevel=1) as cf,gzip.open(HERE/f'events_{k}.gz','wt',encoding='utf8',compresslevel=1) as ef:
        for task in rows(HERE/f'source_{k}.jsonl.gz'):
            iid=task['instance'];static={'instance':iid,'issue':task['issue']}
            states={a:encode(['mixed',0,[],[],[]],ALG[a],LAYOUT[a]) for a in ARMS}
            for t,event in enumerate(task['events'],1):
                cut=t%4==0 and t<len(task['events']); cuts={}; metrics={}
                for a in ARMS:
                    memory.pack=lambda state,_,a=a:encode(state,ALG[a],LAYOUT[a])
                    tick=time.process_time_ns()
                    blob,fit=memory.transition('cal_neighbor',states[a],event,static,ws,BUDGET)
                    delta=time.process_time_ns()-tick
                    assert len(blob)<=BUDGET and len(blob)==fit[1]
                    states[a]=blob
                    metrics[a]=[hashlib.sha256(blob).hexdigest(),*fit,delta]
                    if cut:
                        state=decode(blob);assert t==state[1] and encode(state,ALG[a],LAYOUT[a])==blob
                        cuts[a]=base64.b64encode(blob).decode('ascii')
                write(ef,[iid,t,metrics])
                if cut:write(cf,[iid,t,cuts])
    return k
def score():
    lock=read(HERE/'checkpoint_lock.json')
    assert all(sha(HERE/p)==h for p,h in lock.items())
    out=[];cost={a:collections.Counter() for a in ARMS}
    funnel=collections.Counter();repo_tasks=collections.Counter()
    with gzip.open(HERE/'inspection.jsonl.gz','wt',encoding='utf8') as of:
        for k in range(8):
            cuts=iter(rows(HERE/f'cuts_{k}.gz'))
            for iid,j,metrics in rows(HERE/f'events_{k}.gz'):
                for a,(digest,pre,length,dropped,attempts,cpu) in metrics.items():
                    c=cost[a];c['steps']+=1;c['cpu_ns']+=cpu;c['mean_bytes_total']+=length
                    c['max_bytes']=max(c['max_bytes'],length);c['overfull_before_fit']+=pre>BUDGET
            for task in rows(HERE/f'source_{k}.jsonl.gz'):
                iid=task['instance'];repo=task['official_repo'];ev=task['events'];repo_tasks[repo]+=1
                for t in range(4,len(ev),4):
                    i,j,encoded=next(cuts); assert (i,j)==(iid,t)
                    x={a:decode(base64.b64decode(encoded[a])) for a in ARMS}
                    sizes={a:len(encode(x['generic'],ALG[a],LAYOUT[a])) for a in ARMS}
                    for a,xx in x.items():
                        c=cost[a];c['cuts']+=1;c['resident_lines_sum']+=linecount(xx)
                        c['same_state_bytes_sum']+=sizes[a]
                    write(of,[i,t,sizes,{a:linecount(xx) for a,xx in x.items()}])
                    funnel['cuts']+=1;args,obs=anchor.future_check(ev,t)
                    if not args: continue
                    funnel['attempts']+=1
                    if not anchor.success(args.get('command'),anchor.rel(args.get('path')),obs):continue
                    funnel['confirmed']+=1;gt=anchor.invert(args,obs)
                    if not gt: continue
                    funnel['evaluable']+=1;lo,lines=gt;p=anchor.rel(args['path']);scores={}
                    for a,xx in x.items():
                        mem=prior.materialize(xx)[1]['rebase'].get(p,{})
                        ok=[mem.get(lo+j,[None])[0]==s for j,s in enumerate(lines)]
                        scores[a]=[int(all(ok)),sum(ok)/len(ok),int(ok[0])]
                    out.append([iid,repo,t,len(lines),scores])
            assert next(cuts,None) is None
    with gzip.open(HERE/'scored.jsonl.gz','wt',encoding='utf8') as g:
        for q in out:write(g,q)
    counts={a:sum(q[-1][a][0] for q in out) for a in ARMS}
    details={a:[float(np.mean([q[-1][a][j] for q in out])) for j in range(3)] for a in ARMS}
    contrasts={};r=np.random.default_rng(90518)
    for a,b in [('edges','generic'),('generic','legacy'),('edges','legacy')]:
        comp=anchor.paired(out,a,b)
        ids=sorted({q[0] for q in out})
        z=np.array([[sum(q[-1][a][0]-q[-1][b][0] for q in out if q[0]==i),sum(q[0]==i for q in out)] for i in ids])
        boot=z[r.integers(len(ids),size=(10000,len(ids)))].sum(1)
        comp['ci_unstratified_issues']=np.quantile(boot[:,0]/boot[:,1],[.025,.975]).tolist()
        # Exact convolution over connected task clusters, including ties implicitly.
        dist={0:1}
        for delta in z[:,0]:
            if not delta:continue
            nxt=collections.Counter()
            for v,n in dist.items():nxt[v+int(delta)]+=n;nxt[v-int(delta)]+=n
            dist=nxt
        comp['exact_signflip_task']=sum(n for v,n in dist.items() if abs(v)>=abs(int(z[:,0].sum())))/sum(dist.values())
        contrasts[a+'-'+b]=comp
    save(HERE/'results.json',dict(arms=ARMS,model=BEST,counts=counts,metrics_full_coverage_first=details,unique_scored_tasks=len({q[0] for q in out}),repo_tasks=repo_tasks,repo_tasks_scored=collections.Counter({g:len({q[0] for q in out if q[1]==g}) for g in repo_tasks}),cost=cost,funnel=funnel,contrasts=contrasts))
    print(funnel,counts,contrasts['edges-generic'])
def main():
    import brotli, zlib
    os.environ['OPENBLAS_NUM_THREADS']='1'
    files=[HERE/p for p in ['PROTOCOL.md','sample.py','schema_codec.py','run.py','dev.json','roster_lock.json','receipts.json']]
    files+=[OLD/'memory.py',OLD/'risk.py',OLD/'anchor'/'run_anchor.py',OLD/'risk_model.json',OLD/'python_prior.bin']
    files+=list(HERE.glob('source_*.jsonl.gz'))
    mode=sys.argv[1]
    if mode=='predict':
        assert not (HERE/'checkpoint_lock.json').exists()
        save(HERE/'method_lock.json',dict(files={str(p):sha(p) for p in files},python=sys.version,platform=platform.platform(),brotli=brotli.__version__,numpy=np.__version__,zlib=zlib.ZLIB_VERSION,budget=BUDGET))
        with ProcessPoolExecutor(3) as pool:
            for k in pool.map(predict,range(8)):print('completed shard',k,flush=True)
        outputs=[p for g in ('cuts_*.gz','events_*.gz') for p in HERE.glob(g)]
        assert len(outputs)==16
        save(HERE/'checkpoint_lock.json',{p.name:sha(p) for p in outputs})
    elif mode=='score':score()
    else:raise ValueError(mode)
if __name__=='__main__':main()

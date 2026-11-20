"""Join frozen reads with independently counted current snapshots. Report every comparison."""
import collections,gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
from policy import METHODS
from run import ROOT,source
F=['n','files','bytes','wrong','full_reuse','changed','previous_empty']
def compute():
    cons=json.loads((ROOT/'decision_lock.json').read_bytes())
    for n,h in cons.items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
    hist={};truth={}
    for path in sorted((ROOT/'projection').glob('*.gz')):
        gp=ROOT/'gold'/path.name;ix={(r['repo'],r['step']):r['result'] for r in source(gp)}
        stem=path.name.split('.')[0];ni=ROOT/'natural'/(stem+'_inputs.gz')
        extra={r['step']:r['queries'] for r in source(ni)} if ni.exists() else {}
        if extra:
            for g in source(ROOT/'natural'/(stem+'_gold.gz')):
                origin=ix[g['repo'],g['step']]
                assert all(t not in origin or vs==origin[t] for t,vs in g['result'].items());origin.update(g['result'])
        for r in source(path):
            qs={q['t']:q['prior'] for q in r['queries']+extra.get(r['step'],[])}
            hist[r['repo'],r['step']]=(r['files'],qs)
        truth.update(ix)
    sums=collections.defaultdict(collections.Counter)
    for d in source(ROOT/'decisions.jsonl.gz'):
        repo,step,t,arm,b=d['repo'],d['step'],d['t'],d['arm'],d['budget']
        fs,qs=hist[repo,step];gold=set(truth[repo,step][t]);old=set(qs[t]);tomb={f['p'] for f in fs if not f['new_bytes']}
        for m,ix in d['read'].items():
            got=set(old) if m=='ignore' else old-tomb
            for i in ix:
                p=fs[i]['p']
                if p in gold:got.add(p)
                else:got.discard(p)
            wrong=int(got!=gold);assert not wrong or m=='ignore',(d,m)
            for k in ([arm,'primary'] if arm!='agent' else [arm]):
                c=sums[repo,k,b,m]
                for f,v in zip(F,(1,len(ix),sum(fs[i]['new_bytes'] for i in ix),wrong,int(not ix),int(gold!=old),int(not old))):c[f]+=v
    totals={};intervals={};rng=np.random.default_rng(18112026)
    for k in ('primary','recent','background','agent'):
        repos=sorted({r for r,arm,_,_ in sums if arm==k});idx=rng.integers(0,len(repos),(10000,len(repos)))
        for b in (128,512,2048):
            z={}
            for m in METHODS:
                c=sum((sums[r,k,b,m] for r in repos),collections.Counter())
                for f in F:c.setdefault(f,0)
                z[m]=dict(c)
            totals[k,str(b)]=z
            comps={}
            for m,base in [('count','net'),('count','signed'),('max','count'),('levels','signed'),('hybrid','signed'),('hybrid','levels'),('flips','hybrid'),('subscriptions','hybrid')]:
                ds=np.array([sums[r,k,b,m]['files']-sums[r,k,b,base]['files'] for r in repos]);ns=np.array([sums[r,k,b,m]['n'] for r in repos])
                per=ds/ns
                comps[m+' minus '+base]={'micro_delta_files_per_query':ds.sum()/ns.sum(),'micro_cluster_ci':np.quantile(ds[idx].sum(axis=1)/ns[idx].sum(axis=1),[.025,.975]).tolist(),'project_mean_delta':per.mean(),'project_mean_ci':np.quantile(per[idx].mean(axis=1),[.025,.975]).tolist(),'project_better':int(sum(ds<0)),'project_worse':int(sum(ds>0))}
            intervals[k,str(b)]=comps
    wire=json.loads(gzip.decompress((ROOT/'wire_costs.json.gz').read_bytes()));sel=[r for r in wire if r['budget']==512]
    return {'coverage':{k:len({r for r,a,_,_ in sums if a==k}) for k in ('primary','agent')},'totals':{k:{b:totals[k,b] for b in ('128','512','2048')} for k in ('primary','recent','background','agent')},'intervals':{k:{b:intervals[k,b] for b in ('128','512','2048')} for k in ('primary','recent','background','agent')},
            'per_project':{'|'.join(map(str,key)):dict(v) for key,v in sorted(sums.items())},'wire_sum_all_rosters':{n:sum(r[n] for r in sel) for n in sel[0] if n not in ('repo','step','budget')},'commits':len(sel),'exact_fit512':sum(r['exact_compressed']<=512 for r in sel)}
if __name__=='__main__':
    out=compute();f=ROOT/'results.json'
    if '--verify' in sys.argv:assert json.loads(f.read_bytes())==out;print('PASS all exact post-edit answers; totals, read bytes and project paired intervals')
    else:
        f.write_text(json.dumps(out,indent=1))
        for k in ('primary','agent'):
            print(k,{a:v['files'] for a,v in out['totals'][k]['512'].items()},out['totals'][k]['512']['ignore'],out['intervals'][k]['512']['count minus net'])

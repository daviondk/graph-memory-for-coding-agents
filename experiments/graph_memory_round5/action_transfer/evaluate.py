import base64,collections,gzip,json,math,sys
from replicate import HERE,bound,anchor,read,save,sha,rows,write,digest,np
def pair(data,a,b):
    groups=sorted({r['id'] for r in data});index={i:j for j,i in enumerate(groups)}
    w=np.zeros((len(groups),2),dtype=int);wins=loss=0;per=collections.defaultdict(lambda:[0,0,0])
    for r in data:
        x=r['m'][a][0]-r['m'][b][0];w[index[r['id']]] += (x,1)
        wins+=x>0;loss+=x<0;v=per[r['repo']];v[0]+=x;v[1]+=1;v[2]+=int(x!=0)
    rng=np.random.default_rng(19055);boot=w[rng.integers(len(w),size=(10000,len(w)))].sum(1)
    ci=np.quantile(boot[:,0]/boot[:,1],[.025,.975]);dist={0:1}
    for x in w[:,0]:
        if not x:continue
        new=collections.Counter()
        for y,n in dist.items():new[y+int(x)]+=n;new[y-int(x)]+=n
        dist=new
    net=int(w[:,0].sum());p=sum(n for y,n in dist.items() if abs(y)>=abs(net))/sum(dist.values())
    return dict(count=len(data),wins=wins,losses=loss,net=net,delta=net/len(data),ci=ci.tolist(),p=p,per_repo=dict(per))
def main():
    seal=read(HERE/'decisions_lock.json');assert all(sha(HERE/k)==v for k,v in seal['files'].items())
    files=read(HERE/'method_lock.json')['files'];assert all(sha(k)==v for k,v in files.items())
    out=[];funnel=collections.Counter();check=collections.Counter();checksids=collections.defaultdict(set)
    for k in range(8):
        finite=iter(rows(HERE/f'bounded_cuts_{k}.gz'));inf=iter(rows(HERE/f'unbounded_{k}.gz'))
        for iid,t,kind,a,p,n,ok in rows(HERE/f'confirmation_{k}.gz'):check[f'{kind}_{a}_{ok}']+=1;checksids[f'{kind}_{a}'].add(iid)
        for task in rows(HERE/f'source_{k}.gz'):
            iid=task['instance'];evs=task['events'];funnel['tasks']+=1
            for t in range(4,len(evs),4):
                i1,t1,blob=next(finite);i2,t2,tables=next(inf);assert (iid,t)==(i1,t1)==(i2,t2)
                funnel['cuts']+=1;a,obs=anchor.future_check(evs,t)
                if not a:continue
                funnel['attempt']+=1
                p=anchor.rel(a.get('path'))
                if not anchor.success(a.get('command'),p,obs):continue
                funnel['confirmed']+=1
                gt=anchor.invert(a,obs)
                if not gt:continue
                lo,ls=gt;funnel['evaluable']+=1;m={}
                for arm,pack in blob.items():
                    bb=base64.b64decode(pack);assert 1<len(bb)<=4096
                    x=bound.decode(bb[1:]); assert x[1]==t
                    mem=bound.prior.materialize(x)[1]['rebase'].get(p,{})
                    v=[mem.get(lo+j,[None])[0]==s for j,s in enumerate(ls)]
                    m['cap_'+arm]=[int(all(v)),sum(v)/len(v)]
                for arm,paths in tables.items():
                    mem=dict(paths.get(p,[]));v=[mem.get(lo+j)==digest(s) for j,s in enumerate(ls)]
                    m['free_'+arm]=[int(all(v)),sum(v)/len(v)]
                out.append(dict(id=iid,repo=task['official_repo'],t=t,n=len(ls),m=m))
        assert next(finite,None) is None and next(inf,None) is None
    with gzip.open(HERE/'scores.jsonl.gz','wt',encoding='utf8') as fp:
        for r in out:write(fp,r)
    methods={a:{'hits':sum(r['m'][a][0] for r in out),'full':np.mean([r['m'][a][0] for r in out]),'average_lines':np.mean([r['m'][a][1] for r in out])} for a in out[0]['m']}
    pairs=[(f'{c}_address',f'{c}_{alt}') for c in ('cap','free') for alt in ('base','offset')]
    pairs += [('cap_lru_address','cap_lru_editor'),('cap_address','cap_lru_address'),('cap_base','cap_lru_editor'),('cap_offset','cap_base')]
    cost={}
    for arm in seal['shard_cost'][0]:
        n=sum(x[arm]['steps'] for x in seal['shard_cost']);cost[arm]=dict(steps=n,average_bytes=sum(x[arm]['bytes'] for x in seal['shard_cost'])/n,max_bytes=max(x[arm]['max'] for x in seal['shard_cost']))
    result=dict(funnel=funnel,n_scored_issues=len(set(q['id'] for q in out)),methods=methods,comparisons={a+'-'+b:pair(out,a,b) for a,b in pairs},projection=seal['parser'],later_observations=check,later_task_counts={k:len(s) for k,s in checksids.items()},cost=cost)
    save(HERE/'results.json',result)
    print(funnel,methods,result['comparisons']['cap_address-cap_base'])
if __name__=='__main__':main()

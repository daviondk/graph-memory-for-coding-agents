import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('r5_causal_projection',Path(__file__).with_name('policy.py'));pol=importlib.util.module_from_spec(spec);spec.loader.exec_module(pol)
globals().update({k:v for k,v in vars(pol).items() if not k.startswith('_')})
import numpy as np
def anyspan(block,span):
    n=len(block)
    return len(span)>=n and any(span[i:i+n]==block for i,x in enumerate(span) if x==block[0])
def flags(old,cur,prior,groups,raw,args,p,lo,g):
    match=lambda mp:[mp.get((p,lo+i))==s for i,s in enumerate(g)]
    policies={a:match(m) for a,m in cur.items()}
    hist=[prior.get((p,lo+i)) for i in range(len(g))]
    policies['last_when_missing']=[cur['base'].get((p,lo+i),v)==g[i] for i,v in enumerate(hist)]
    sameaddr=all(v in old.get((p,lo+i),set()) for i,v in enumerate(g))
    same=any(anyspan(g,vals) for pp,_,vals in groups if pp==p)
    other=any(anyspan(g,vals) for pp,_,vals in groups if pp!=p)
    terminal=any(anyspan(g,vals) for vals in raw)
    inargs=any(anyspan(g,vals) for vals in args)
    e={s for pp,n,vals in groups for s in vals};b={s for vals in raw for s in vals};a={s for vals in args for s in vals}
    all_lines=all(s in e|b for s in g);editor_lines=all(s in e for s in g)
    cls=next(key for key,ok in [('historical_same_address',sameaddr),('editor_same_file',same),('editor_other_file',other),('terminal_contiguous',terminal),('separate_lines',all_lines),('missing_line',True)] if ok)
    return dict(methods={a:dict(full=all(v),hits=sum(v)) for a,v in policies.items()},oracle=dict(category=cls,same_address=sameaddr,same_file=same,other_file=other,terminal_block=terminal,fragment_lines=all_lines,editor_lines=editor_lines,argument_block=inargs,all_with_arguments=all(s in e|b|a for s in g),missing_lines=sum(s not in e|b for s in g)))
def effect(data,a,b):
    names=sorted({r['id'] for r in data});ids={k:i for i,k in enumerate(names)};g=np.array([ids[r['id']] for r in data]);v=np.array([int(r['methods'][a]['full'])-int(r['methods'][b]['full']) for r in data]);n=np.bincount(g);s=np.bincount(g,weights=v);draw=np.random.default_rng(31118).integers(len(n),size=(10000,len(n)));ci=np.quantile(s[draw].sum(1)/n[draw].sum(1),[.025,.975]).tolist()
    return dict(delta=v.mean(),ci=ci,wins=int((v>0).sum()),losses=int((v<0).sum()))
def main():
    lock=read(D/'decision_lock.json')
    assert all(h((D/f).read_bytes())==x for f,x in lock['files'].items())
    original={(id,cut):(when,limited,start,last) for id,cut,when,p,lo,n,limited,start,last in rr(W/'headroom.jsonl.gz')}
    edges=iter(rr(D/'decisions.jsonl.gz'));hist=iter(rr(D/'observed.jsonl.gz'));out=[];valid=[]
    for k in range(8):
        for task in rr(W/f'source_{k}.jsonl.gz'):
            iid=task['instance'];events=task['events'];requests=defaultdict(list);cache={a:{} for a in ('base','address','offset')};prior={};old=defaultdict(set);pages=[];bash=[];argbuf=[];validated=set()
            for t in range(4,len(events),4):
                if (iid,t) not in original:continue
                when,lim,start,last=original[iid,t];args,obs=anchor.future_check(events,t)
                assert args is events[when][1];lo,g=anchor.invert(args,obs);p=anchor.rel(args['path'])
                meta=dict(id=iid,repo=task['official_repo'],cut=t,when=when,path=p,lo=lo,n=len(g),nontrivial=any(sum(s.isalnum() for s in line)>=8 for line in g))
                for point,at,ref in [('cut',t,start),('before',when,last)]:requests[at].append((meta,point,[token(s) for s in g],ref))
            for j,ev in enumerate(events,1):
                id1,step,changes=next(edges);id2,step2,editor,other,arguments=next(hist)
                assert (id1,step)==(id2,step2)==(iid,j)
                for meta,point,g,ref in requests[j-1]:
                    row={**meta,'point':point,**flags(old,cache,prior,pages,bash,argbuf,meta['path'],meta['lo'],g)}
                    assert int(row['methods']['base']['full'])==ref
                    out.append(row)
                _,a,obs=ev;p=anchor.rel(a.get('path'))
                if anchor.success(a.get('command'),p,obs) and (m:=anchor.unique_new(a,obs)):
                    first,block,pos=m;lo=first+block[:pos].count('\n');end=lo+a.get('new_str','').count('\n');shift=a.get('new_str','').count('\n')-a['old_str'].count('\n')
                    for n,s in anchor.printed(obs).items():
                        if lo<=n<=end:continue
                        oldn=n if n<lo else n-shift
                        k0=p,oldn
                        for arm in ('address','offset'):
                            z=cache[arm].get(k0);key=(arm,k0,z)
                            if z is not None and z!=cache['base'].get(k0) and key not in validated:
                                validated.add(key);valid.append([iid,task['official_repo'],j,arm,p,oldn,z==token(s)])
                for a,ls in changes.items():
                    for p,n,v in ls:
                        if v is None:cache[a].pop((p,n),None)
                        else:cache[a][p,n]=v
                for p,n,ls in editor:
                    for i,s in enumerate(ls):prior[p,n+i]=s;old[p,n+i].add(s)
                pages+=editor;bash+=other;argbuf+=arguments
    assert len(out)==506 and next(edges,None) is None and next(hist,None) is None
    with gzip.open(D/'items.jsonl.gz','wt',encoding='utf8') as g:
        for row in out:write(g,row)
    with gzip.open(D/'neighbors.jsonl.gz','wt',encoding='utf8') as g:
        for row in valid:write(g,row)
    res={}
    for point in ('cut','before'):
        select=[r for r in out if r['point']==point];seq=[r for r in select if not r['methods']['base']['full']]
        groups={}
        for name,slice_ in [('all',select),('old_miss',seq),('nontrivial_miss',[r for r in seq if r['nontrivial']])]:
            groups[name]=dict(n=len(slice_),by_category=dict(Counter(r['oracle']['category'] for r in slice_)),flags={a:sum(r['oracle'][a] for r in slice_) for a in ('same_address','same_file','other_file','terminal_block','fragment_lines','editor_lines','argument_block','all_with_arguments')},methods={a:dict(full=sum(r['methods'][a]['full'] for r in slice_),fraction=np.mean([r['methods'][a]['hits']/r['n'] for r in slice_])) for a in select[0]['methods']})
        res[point]=dict(coverage=groups,paired={a+'-'+b:effect(select,a,b) for a,b in [('address','base'),('address','offset'),('last_when_missing','base')]})
    save('result.json',dict(points=res,views=Counter((str(x[-1])+'_'+x[3]) for x in rr(D/'views.jsonl.gz')),neighbors=Counter((str(x[-1])+'_'+x[3]) for x in valid),issues=len({r['id'] for r in out}),repos=len({r['repo'] for r in out}),items=h((D/'items.jsonl.gz').read_bytes())))
if __name__=='__main__':main()


"""Evaluate sealed prior states. No policy uses any part of this module."""
import base64
import collections
import gzip
import hashlib
import json

import numpy as np
import replay
from replay import HERE, old, ARMS, PANELS, inputs, jobs
from version_policy import mutations, next_root


def maps(blobs):
    return {a:old.prior.materialize(old.decode(base64.b64decode(blob)[1:]))[1]['rebase'] for a,blob in blobs.items()}


def classifications(mem,p,n,s):
    return [0 if (v:=mem[a].get(p,{}).get(n)) is None else 1 if v[0]==s else 2 for a in ARMS]


def future_observations(event,extra,root):
    _,args,obs=event
    p=old.anchor.rel(args.get('path'))
    out={(path,n):(v,'terminal') for path,n,v,_ in old.pol.readlines(extra,root)}
    if p and args.get('command')=='view':
        out.update({(p,n):(s,'view') for n,s in old.anchor.printed(obs).items()})
    elif p and old.anchor.success(args.get('command'),p,obs) and (m:=old.anchor.unique_new(args,obs)):
        first,block,pos=m
        lo=first+block[:pos].count('\n')
        shift=args.get('new_str','').count('\n')-args['old_str'].count('\n')
        last=lo+args.get('new_str','').count('\n')
        for n,s in old.anchor.printed(obs).items():
            if n<lo or n>last:
                out[p,n if n<lo else n-shift]=s,'neighbor'
    return out


def paired(data,a,b,num,den):
    ids=sorted({r['id'] for r in data})
    idx={i:j for j,i in enumerate(ids)}
    vec=np.zeros((len(ids),2),dtype=np.int64)
    win=lose=0
    for r in data:
        delta=num(r,a)-num(r,b)
        vec[idx[r['id']]] += [delta,den(r)]
        win+=delta>0;lose+=delta<0
    if not len(vec) or not vec[:,1].sum():
        return None
    rng=np.random.default_rng(67231)
    samples=vec[rng.integers(len(vec),size=(10000,len(vec)))].sum(1)
    eligible=samples[:,1]>0
    boot=samples[eligible,0]/samples[eligible,1]
    net,total=map(int,vec.sum(0))
    return dict(net=net,denominator=total,rate=net/total,ci=np.quantile(boot,[.025,.975]).tolist(),n_tasks=len(ids),nonzero_tasks=int(np.count_nonzero(vec[:,0])),wins=int(win),losses=int(lose))


def main():
    replay.check('method_lock.json')
    replay.check('state_lock.json')
    assert json.loads((HERE/'state_lock.json').read_bytes())['method_sha']==replay.digest(HERE/'method_lock.json')
    edits=[]; audits=[];summary={}
    with gzip.open(HERE/'block_outcomes.jsonl.gz','wt',encoding='utf8') as bo, gzip.open(HERE/'address_audit.jsonl.gz','wt',encoding='utf8') as ao,gzip.open(HERE/'operations.jsonl.gz','wt',encoding='utf8') as so:
        for panel in PANELS:
            counts=collections.Counter()
            costs={a:collections.Counter() for a in ARMS}
            for _,k in (job for job in jobs() if job[0]==panel):
                src,pair=inputs(panel,k);raw=dict(old.rr(pair))
                snaps=iter(old.rr(HERE/f'states_{panel}_{k}.gz'))
                for q in old.rr(src):
                    iid=q['instance'];counts['tasks']+=1
                    prev={a:{} for a in ARMS}
                    root=True;versions={};seen=set();shell_ever={}
                    for t,(event,extra) in enumerate(zip(q['events'],raw[iid],strict=True),1):
                        counts['steps']+=1
                        assertions=future_observations(event,extra,root)
                        local=collections.defaultdict(lambda:np.zeros((len(ARMS),3),dtype=int))
                        for (p,n),(s,source) in assertions.items():
                            epoch,writer=versions.get(p,(0,'initial'))
                            key=(p,n,epoch)
                            if key in seen: continue
                            seen.add(key)
                            z=classifications(prev,p,n,s)
                            for j,code in enumerate(z):
                                local[writer=='shell'][j,code]+=1
                            old.write(ao,[panel,iid,t,p,n,epoch,writer,source,hashlib.sha256(s.encode()).hexdigest(),z])
                        for touched,mat in local.items():
                            audits.append(dict(panel=panel,id=iid,shell=touched,mat={a:v.tolist() for a,v in zip(ARMS,mat)}))
                        actions=mutations(extra,root)
                        for p,kind,expr in actions:
                            versions[p]=(t,'shell')
                            shell_ever[p]=t
                            old.write(so,[panel,iid,t,p,kind,hashlib.sha256(expr.encode()).hexdigest(),len(prev['r5'].get(p,{}))])
                        _,args,obs=event
                        p=old.anchor.rel(args.get('path'))
                        if p and (old.anchor.success(args.get('command'),p,obs) or args.get('command') in ('create','insert','undo_edit')):
                            versions[p]=(t,'editor')
                        root=next_root(root,extra)
                        i,j,blobs,profile=next(snaps);assert (i,j)==(iid,t)
                        prev=maps(blobs)
                        for a,(cpu,n,stat) in profile.items():
                            assert n<=4096
                            costs[a]['cpu_ns']+=cpu;costs[a]['bytes']+=n
                            costs[a]['max_bytes']=max(costs[a]['max_bytes'],n)
                            costs[a].update(stat)
                        if t%4 or t==len(q['events']):continue
                        counts['cuts']+=1
                        args,obs=old.anchor.future_check(q['events'],t)
                        if not args:continue
                        counts['attempts']+=1
                        p=old.anchor.rel(args.get('path'))
                        if not old.anchor.success(args.get('command'),p,obs):continue
                        counts['confirmed']+=1
                        if not (target:=old.anchor.invert(args,obs)):continue
                        lo,ls=target
                        allcodes=[classifications(prev,p,lo+j,s) for j,s in enumerate(ls)]
                        result={}
                        for a,col in zip(ARMS,zip(*allcodes,strict=True),strict=True):
                            result[a]=dict(full=int(all(x==1 for x in col)),correct=col.count(1),wrong=col.count(2),missing=col.count(0))
                        r=dict(panel=panel,id=iid,repo=q['official_repo'],cut=t,path=p,line=lo,n=len(ls),latest_writer=versions.get(p,(0,'initial'))[1],last_shell=shell_ever.get(p),out=result)
                        old.write(bo,r);edits.append(r)
                assert next(snaps,None) is None
            label=[r for r in edits if r['panel']==panel]
            checks=[r for r in audits if r['panel']==panel]
            counts['scored_tasks']=len({r['id'] for r in label})
            counts['scored_blocks']=len(label)
            counts['same_path_prior_shell']=sum(r['last_shell'] is not None for r in label)
            counts['same_path_latest_shell']=sum(r['latest_writer']=='shell' for r in label)
            res=dict(funnel=counts,blocks={},cost=costs,audit={},contrasts={})
            for a in ARMS:
                rows=[r['out'][a] for r in label]
                res['blocks'][a]={v:sum(z[v] for z in rows) for v in ['full','correct','wrong','missing']}
                res['blocks'][a]['macro_line_hit']=float(np.mean([r['out'][a]['correct']/r['n'] for r in label]))
                costs[a]['mean_bytes']=costs[a]['bytes']/counts['steps']
                costs[a]['mean_cpu_ms']=costs[a]['cpu_ns']/counts['steps']/1e6
            for subset,rows in [('all',checks),('shell_epoch',[r for r in checks if r['shell']])]:
                mat={a:[sum(r['mat'][a][j] for r in rows) for j in range(3)] for a in ARMS}
                res['audit'][subset]=dict(tasks=len({r['id'] for r in rows}),counts_missing_correct_wrong=mat)
                res['audit'][subset]['wrong_per_address_transport_minus_r5']=paired(rows,'transport','r5',lambda r,a:r['mat'][a][2],lambda r:sum(r['mat']['r5']))
            for a,b in [('transport','r5'),('invalidate','r5'),('transport','invalidate'),('transport','lru'),('r5','lru')]:
                res['contrasts'][a+'-'+b]=paired(label,a,b,lambda r,a:r['out'][a]['full'],lambda r:1)
            summary[panel]=res
    replay.save('results.json',summary)
    replay.save('evaluation_lock.json',dict(utc=old.stamp(),files=replay.locks([HERE/f for f in ['state_lock.json','results.json','address_audit.jsonl.gz','block_outcomes.jsonl.gz','operations.jsonl.gz']])))
    print(json.dumps({p:v['contrasts']['transport-r5'] for p,v in summary.items()}))


if __name__=='__main__':
    main()

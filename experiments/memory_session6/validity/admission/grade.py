from collections import Counter,defaultdict
from common import *
def expected_hit(u,r,k):
    slots=min(k,u)
    return 0.0 if not r or not slots else 1-math.comb(u-r,slots)/math.comb(u,slots)
def positive(x):return int(bool(x))
def combine(target,src):
    for key,s in src.items(): target[key].update(s)
def views(data):return {k:dict(v) for k,v in data.items()}
def main():
    sourcecheck();lock=read('decision_lock.json');assert digest((ROOT/'decisions.jsonl.gz').read_bytes())==lock['decisions_sha']
    group=defaultdict(lambda:defaultdict(Counter));projects=defaultdict(lambda:defaultdict(Counter));census=defaultdict(Counter)
    totals=Counter();seen_rows=set()
    with (ROOT/'trajectory.jsonl.gz').open('wb') as fh,gzip.GzipFile(filename='',fileobj=fh,mode='wb',mtime=0) as out:
        for r,log in zip(rows(INPUT),rows(ROOT/'decisions.jsonl.gz'),strict=True):
            sh,rn,ms,repo,split,dec=log; assert [sh,rn,ms,repo]==[r['shard'],r['row'],r['messages_sha'],r['repo']]
            assert (sh,rn) not in seen_rows;seen_rows.add((sh,rn))
            per=defaultdict(Counter); den=Counter(trajectories=1,shell_calls=r['shell_calls'],edits=r['edits'],literal_calls=len(dec),with_literal=positive(dec),with_edit=positive(r['edits']))
            last={'cmd':{},'id':{}};handles=defaultdict(dict)
            for event,entry in zip(r['literal_calls'],dec,strict=True):
                tick,edits,cmd,terms=event; assert entry[:2]==[tick,edits];dt=iter(entry[2])
                for kind,keys in [('cmd',[cmd]),('id',sorted(set(terms)))]:
                    prior=last[kind];repeat={x for x in keys if x in prior};stale={x for x in repeat if prior[x]<edits}
                    den[kind+'_key_probes']+=len(keys);den[kind+'_repeat']+=positive(repeat);den[kind+'_after_edit']+=positive(stale)
                    u=len(prior)
                    for k in (1,2,4):
                        for p in NAMES:
                            hits,adds,writes,ghosts,evicted,promotions,resident=next(dt);idn=f'{kind}/{k}/{p}';s=per[idn]
                            assert set(hits)<=repeat and len(resident)<=k
                            s['hits']+=positive(hits); s['key_hits']+=len(hits); s['after_edit_hits']+=positive(set(hits)&stale)
                            s['enrollments']+=len(adds);s['metadata_updates']+=len(writes);s['ghost_installs']+=len(ghosts);s['evictions']+=len(evicted);s['promotions']+=len(promotions)
                            active=handles[idn]
                            for x in hits:
                                assert x in active
                                if not active[x][0]:s['productive_enrollments']+=1;active[x][0]=True
                                if x in stale and not active[x][1]:s['productive_after_edit']+=1;active[x][1]=True
                            for x in adds:active[x]=[False,False]
                            handles[idn]={x:active[x] for x in resident}
                        s=per[f'{kind}/{k}/uniform_exact']
                        s['hits']+=expected_hit(u,len(repeat),k);s['after_edit_hits']+=expected_hit(u,len(stale),k)
                        s['key_hits']+=min(1,k/u)*len(repeat) if u else 0
                        add=sum(min(1,k/j) for j in range(u+1,u+len(keys)-len(repeat)+1))
                        s['enrollments']+=add;s['metadata_updates']+=add
                    for x in keys:prior[x]=edits
                try:next(dt);raise ValueError('unexpected trailing decision')
                except StopIteration:pass
            for kind in ('cmd','id'):
                for key in ('repeat','after_edit'):den[f'trajs_{kind}_{key}']=positive(den.get(kind+'_'+key))
                for k in (1,2,4):
                    for p in (*NAMES,'uniform_exact'):
                        a=per[f'{kind}/{k}/{p}']
                        a['trajectories_with_hit']=int(a['hits']>0) if p!='uniform_exact' else 0
                        a['trajectories_with_after_edit_hit']=int(a['after_edit_hits']>0) if p!='uniform_exact' else 0
                        assert a['hits']<=den[kind+'_repeat']+1e-8 and a['after_edit_hits']<=den[kind+'_after_edit']+1e-8
                        if p!='uniform_exact':assert a['productive_enrollments']<=a['enrollments'] and a['productive_after_edit']<=a['productive_enrollments']
            for key in ('all',split):
                combine(group[key],per);census[key].update(den)
            combine(projects[repo],per);census['repo:'+repo].update(den);totals.update(den)
            out.write((canon(dict(shard=sh,row=rn,messages_sha=ms,repo=repo,split=split,issue=r['issue'],den=den,metrics=views(per)))+'\n').encode())
    write('results.json',{'cohorts':{k:views(v) for k,v in group.items()},'denominators':{k:dict(v) for k,v in census.items() if not k.startswith('repo:')},'repositories':len(projects)})
    write('projects.json',{k:{'den':census['repo:'+k],'metrics':views(v)} for k,v in projects.items()})
    print(canon(totals))
if __name__=='__main__': main()


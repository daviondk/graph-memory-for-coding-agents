import base64
import collections
import gzip
import json
import numpy as np
from run_codec import HERE,old,check,write,ARMS,JOBS,unpack,lock
import replay
import score as grade


def main():
    check('method_lock.json');check('state_lock.json');replay.check('evaluation_lock.json')
    target={}
    for panel,shard in replay.jobs():
        src,_=replay.inputs(panel,shard)
        for q in old.rr(src):
            for cut in range(4,len(q['events']),4):
                args,obs=old.anchor.future_check(q['events'],cut)
                if args and old.anchor.success(args.get('command'),old.anchor.rel(args.get('path')),obs) and (gold:=old.anchor.invert(args,obs)):
                    target[panel,q['instance'],cut]=(old.anchor.rel(args['path']),*gold)
    previous={(r['panel'],r['id'],r['cut']):r for r in old.rr(HERE.parent/'block_outcomes.jsonl.gz')}
    assert target.keys()==previous.keys()
    records=[];cost=collections.defaultdict(lambda:{a:collections.Counter() for a in ARMS})
    paired_size=collections.defaultdict(collections.Counter)
    with gzip.open(HERE/'scored.jsonl.gz','wt',encoding='utf8') as out:
        for p,k in JOBS:
            for iid,t,blobs,meta in old.rr(HERE/f'codec_{p}_{k}.gz'):
                for panel in ('pooled',p):
                    for arm in ARMS:
                        size,rows,cpu,typ,pre,drop,*extra=meta[arm]
                        c=cost[panel][arm]
                        c.update(dict(bytes=size,lines=rows,steps=1,cpu_ns=cpu,overflow=int(pre>4096),evicted_pages=drop))
                        c['as_'+typ]+=1;c['max_bytes']=max(c['max_bytes'],size)
                    sizes=meta['standard'][-1]
                    paired_size[panel].update(dict(json=sizes[0],edges=sizes[1],binary=sizes[2],best=min(sizes)))
                if not (truth:=target.get((p,iid,t))):continue
                path,lo,ls=truth
                r=dict(panel=p,id=iid,cut=t,n=len(ls),out={})
                for arm,blob in blobs.items():
                    mem=old.prior.materialize(unpack(base64.b64decode(blob)[1:]))[1]['rebase'].get(path,{})
                    codes=[0 if (v:=mem.get(lo+j)) is None else 1 if v[0]==s else 2 for j,s in enumerate(ls)]
                    r['out'][arm]=dict(full=int(all(c==1 for c in codes)),correct=codes.count(1),wrong=codes.count(2),missing=codes.count(0))
                assert r['out']['standard']==previous[p,iid,t]['out']['lru']
                r['out']['graph']=previous[p,iid,t]['out']['r5']
                records.append(r);old.write(out,r)
    result={}
    for p in ('pooled',*replay.PANELS):
        rs=[r for r in records if p=='pooled' or r['panel']==p]
        result[p]=dict(n=len(rs),cost=cost[p],same_state_bytes=paired_size[p],cases={},comparisons={})
        for a in [*ARMS,'graph']:
            result[p]['cases'][a]={m:sum(r['out'][a][m] for r in rs) for m in ('full','correct','wrong','missing')}
        for a,b in [('adaptive','standard'),('adaptive','edges'),('edges','standard'),('adaptive','graph')]:
            result[p]['comparisons'][a+'-'+b]=grade.paired(rs,a,b,lambda r,m:r['out'][m]['full'],lambda r:1)
    write('results.json',result)
    lock('evaluation_lock.json',[HERE/f for f in ('results.json','scored.jsonl.gz','state_lock.json')])
    print(json.dumps(result['pooled']['comparisons']))


if __name__=='__main__':main()

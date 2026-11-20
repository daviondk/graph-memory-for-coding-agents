import base64
import collections
import gzip
import importlib.util
import json
import numpy as np
from find_route import HERE,old,replay,ARMS,lock

spec=importlib.util.spec_from_file_location('version_grade',HERE.parent/'score.py')
grade=importlib.util.module_from_spec(spec);spec.loader.exec_module(grade)


def main():
    for name in ['method_lock.json','answer_lock.json']:
        for p,h in json.loads((HERE/name).read_bytes())['files'].items(): assert replay.digest(HERE/p)==h
    replay.check('evaluation_lock.json')
    predictions={(panel,iid,t):(n,ans,elapsed) for panel,iid,t,n,ans,elapsed in old.rr(HERE/'routes.jsonl.gz')}
    existing={(r['panel'],r['id'],r['cut']):r for r in old.rr(HERE.parent/'block_outcomes.jsonl.gz')}
    rows=[]
    for panel,k in replay.jobs():
        src,_=replay.inputs(panel,k)
        task={q['instance']:q for q in old.rr(src)}
        for iid,t,blobs,_ in old.rr(HERE.parent/f'states_{panel}_{k}.gz'):
            key=(panel,iid,t)
            if key not in existing: continue
            r=existing[key]
            path=r['path'];lo=r['line'];ev=task[iid]['events']
            a,obs=old.anchor.future_check(ev,t);gt,txt=old.anchor.invert(a,obs);assert lo==gt
            mem=old.prior.materialize(old.decode(base64.b64decode(blobs['r5'])[1:]))[1]['rebase']
            n,ans,elapsed=predictions[key]
            scores={}
            for arm in ARMS:
                addr=ans[arm]
                for j in (1,3):
                    subset=addr[:j]
                    saw={v for p,x,y in subset if p==path for v in range(x,y+1)}
                    assert sum(y-x+1 for _,x,y in subset)<=10*j
                    scores[arm+str(j)]=dict(start=int(lo in saw),file=int(any(p==path for p,_,_ in subset)),full=int(all(lo+i in saw and mem[path][lo+i][0]==s for i,s in enumerate(txt))),lines=sum(y-x+1 for _,x,y in subset),near5=int(bool(addr and addr[0][0]==path and abs((addr[0][1]+addr[0][2])//2-lo)<=5)))
            rows.append(dict(panel=panel,id=iid,cut=t,repo=r['repo'],out=scores,reach_start=int(lo in mem.get(path,{})),reach_full=r['out']['r5']['full'],n_windows=n,elapsed_ns=elapsed))
    assert len(rows)==len(existing)
    res={}
    for panel in ('pooled',*replay.PANELS):
        rs=[r for r in rows if panel=='pooled' or r['panel']==panel]
        entry=dict(n=len(rs),n_tasks=len({r['id'] for r in rs}),reachable_start=sum(r['reach_start'] for r in rs),reachable_full=sum(r['reach_full'] for r in rs),methods={},contrasts={})
        for arm in rs[0]['out']:
            entry['methods'][arm]={m:sum(r['out'][arm][m] for r in rs) for m in ('start','file','full','lines','near5')}
        for k in (1,3):
            for a,b in [('combined','recent'),('combined','edited'),('edited','recent')]:
                a+=str(k);b+=str(k)
                entry['contrasts'][a+'-'+b]=grade.paired(rs,a,b,lambda r,arm:r['out'][arm]['start'],lambda r:1)
        res[panel]=entry
    hpath=replay.R5/'next_action/H_items.json.gz'
    older={r['id']:r for r in json.loads(gzip.decompress(hpath.read_bytes()))}
    common=[]
    for r in rows:
        i=r['id']+'|'+str(r['cut'])
        if r['panel']=='probe' and i in older:
            oldr=older[i]; assert oldr['ref']==[existing['probe',r['id'],r['cut']]['path'],existing['probe',r['id'],r['cut']]['line']]
            common.append({**{a:z['near5'] for a,z in oldr['m'].items()},**{a:r['out'][a+'1']['near5'] for a in ARMS}})
    assert len(common)==len(older)==96
    res['H96']=dict(n=len(common),totals={a:sum(r[a] for r in common) for a in common[0]},source_sha=replay.digest(hpath))
    times=[elapsed for n,ans,elapsed in predictions.values()]
    res['prediction_cost']=dict(all_checkpoints=len(predictions),all_three_mean_ms=float(np.mean(times)/1e6),all_three_p95_ms=float(np.quantile(times,.95)/1e6))
    (HERE/'results.json').write_text(json.dumps(res,indent=1))
    with gzip.open(HERE/'scored.jsonl.gz','wt',encoding='utf8') as out:
        for r in rows:old.write(out,r)
    lock('evaluation_lock.json',[HERE/f for f in ['results.json','scored.jsonl.gz','answer_lock.json']]+[hpath])
    print(res['transfer']['contrasts']['combined1-recent1'])


if __name__=='__main__':main()

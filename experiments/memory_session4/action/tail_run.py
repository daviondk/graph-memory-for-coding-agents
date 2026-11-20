"""Frozen chronological extension; original cohort is warmup, no changes to scorers."""
import json, gzip, io, hashlib, heapq
from pathlib import Path
from collections import Counter
from bson_stream import docs
from model import Bank,stable
from run import P,readgz,writegz
from glm import FTRL
def stream_sources():
    data=(P/'restarted_logs.prefix.gz.part').read_bytes()+(P/'restarted_logs.tail128.gz.part').read_bytes()
    result={}
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        try:
            for x in docs(f):
                old=(x.get('analysis') or {}).get('original') or {}
                a=old.get('reasons')
                if not isinstance(a,list):continue
                sig=set()
                for z in a:
                    v=(z.get('category') or z.get('type') or 'unspecified') if isinstance(z,dict) else 'unspecified'
                    sig.add(v.lower().strip()[:64] if isinstance(v,str) else 'unspecified')
                key=x['id']
                if key in result and result[key]!=sorted(sig):result[key]=None
                elif key not in result:result[key]=sorted(sig)
        except EOFError:pass
    return result
def main():
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [P/'TAIL_VALIDATION_PRELOCK.md',P/'tail_run.py',P/'model.py',P/'glm.py',P/'run.py',P/'tail_source.json']}
    seal=P/'tail_input_lock.json'
    if seal.exists():assert json.loads(seal.read_bytes())==hashes
    else:seal.write_text(json.dumps(hashes,indent=1))
    old=readgz(P/'jobs_inputs.jsonl.gz');oldids={r['id'] for r in old};cut=max(r['decision_at'] for r in old)
    y={r['id']:r for r in readgz(P/'jobs_labels.jsonl.gz')};extra=[];reasons=stream_sources();count=Counter()
    with gzip.open(P/'restarted_jobs.bson.gz','rb') as f:
        for d in docs(f):
            i=d['id']
            if i in oldids or i not in reasons or reasons[i] is None:continue
            a,b=d['old'],d['new']
            count['additional_matches']+=1
            if any(a.get(k)!=b.get(k) or a.get(k) is None for k in ['id','repository_id','commit_id']) or a['id']!=i:count['mismatched_identity']+=1;continue
            if a['state'] not in ('failed','errored') or b['state'] not in ('passed','failed','errored'):count['state']+=1;continue
            t=[a.get('started_at'),a.get('finished_at'),b.get('started_at'),b.get('finished_at')]
            if any(not isinstance(k,int) or k<=0 for k in t) or t!=sorted(t):count['time']+=1;continue
            if t[1]<=cut:count['not_after_original_tail']+=1;continue
            r={'id':i,'repo':a['repository_id'],'commit':a['commit_id'],'status':a['state'],'event':a.get('event_type') or 'unknown','language':a.get('language') or 'unknown','matrix':'unknown','decision_at':t[1],'reasons':reasons[i]}
            extra.append(r);y[i]={'id':i,'available_after':t[3],'duration_s':(t[3]-t[2])/1000,'passed':int(b['state']=='passed')}
    extra.sort(key=lambda x:(x['decision_at'],x['id']))
    inputs=sorted(old,key=lambda x:(x['decision_at'],x['id']))+extra;ix={r['id']:r for r in inputs}
    assert len(ix)==len(inputs)
    writegz(P/'tail_inputs.jsonl.gz',inputs);writegz(P/'tail_labels.jsonl.gz',y.values())
    writegz(P/'tail_ids.jsonl.gz',[{'id':r['id']} for r in extra])
    count.update(warm=len(old),heldout=len(extra))
    (P/'tail_cohort.json').write_text(json.dumps(count,indent=1))
    def reveal(b,queue,t,glm=False):
        while queue and queue[0][0]<t:
            _,i=heapq.heappop(queue)
            (b.update if glm else b.add)(ix[i],y[i]['passed'])
    def enq(q,i):heapq.heappush(q,(y[i]['available_after'],i))
    b=Bank();q=[];preds={}
    for r in inputs:
        i=r['id'];reveal(b,q,r['decision_at'])
        if i not in oldids:preds[i]={'id':i,'p':b.scores(r),'selected':[]}
        enq(q,i)
    methods=['random','global','repo','repo_status','recent8','typed','global_type','typed_if_uncertain','typed_if_sparse','glm','glm_type']
    for method in methods:
        glm=method.startswith('glm');b=FTRL(method=='glm_type') if glm else Bank();q=[]
        if glm:
            for r in inputs:
                i=r['id'];reveal(b,q,r['decision_at'],True)
                if i not in oldids:preds[i]['p'][method]=b.p(r)
                enq(q,i)
            b=FTRL(method=='glm_type');q=[]
        for r in old:enq(q,r['id'])
        for j in range(0,len(extra),100):
            group=extra[j:j+100];reveal(b,q,group[0]['decision_at'],glm)
            m=max(1,int(len(group)*.2+.5))
            for r in sorted(group,key=lambda r: (-(b.p(r) if glm else b.scores(r)[method]),stable(r['id'])))[:m]:
                preds[r['id']]['selected'].append(method);enq(q,r['id'])
    writegz(P/'tail_predictions.jsonl.gz',preds.values());print('tail projected and predicted',count)
if __name__=='__main__':main()

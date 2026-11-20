"""Chronological update. No uncompleted outcomes, no write after an unselected threshold/queue action."""
import gzip,heapq,json
from collections import defaultdict
from pathlib import Path
from model import Bank,stable
P=Path(__file__).resolve().parent
def readgz(p):
    with gzip.open(p,'rt',encoding='utf8') as f:return [json.loads(line) for line in f]
def writegz(path,rows):
    with path.open('wb') as fp:
        with gzip.GzipFile(fileobj=fp,mode='wb',mtime=0) as g:
            for r in rows:g.write((json.dumps(r,separators=(',',':'),sort_keys=True)+'\n').encode())
def load(kind):
    r=sorted(readgz(P/(kind+'_inputs.jsonl.gz')),key=lambda x:(x['decision_at'],x['id']))
    y={x['id']:x for x in readgz(P/(kind+'_labels.jsonl.gz'))}
    assert len(y)==len(r)==len({x['id'] for x in r})
    return r,y
def timeline(kind):
    r,labels=load(kind);warm=len(r)//2
    b=Bank();queue=[];n_updates=0;row_by_id={x['id']:x for x in r}
    def add_when_seen(bank,q,t):
        n=0
        while q and q[0][0]<t:
            _,i=heapq.heappop(q);bank.add(row_by_id[i],labels[i]['passed']);n+=1
        return n
    def delay(q,i):
        heapq.heappush(q,(labels[i]['available_after'],i))
    scored=[]
    for j,x in enumerate(r):
        n_updates+=add_when_seen(b,queue,x['decision_at'])
        if j>=warm:scored.append({'id':x['id'],'p':b.scores(x),'available_receipts':n_updates})
        delay(queue,x['id'])
    writegz(P/(kind+'_predictions.jsonl.gz'),scored)
    arms=['random','global','status','repo','repo_status','last_repo','global_context','recent8','context_all']
    if kind=='jobs':arms+=['typed','global_type','typed_if_uncertain','typed_if_sparse']
    main='typed' if kind=='jobs' else 'recent8'
    arms+=['explore_'+main,'teacher_'+main]
    records={x['id']:{'id':x['id'],'accepted':[],'block':j//100} for j,x in enumerate(r[warm:])}
    for arm in arms:
        b=Bank();q=[]
        for x in r[:warm]:delay(q,x['id'])
        key=arm.split('_',1)[1] if arm.startswith(('explore_','teacher_')) else arm
        for j in range(warm,len(r),100):
            group=r[j:j+100];add_when_seen(b,q,group[0]['decision_at'])
            m=max(1,int(len(group)*.2+.5));ranking=sorted(group,key=lambda x:(-b.scores(x)[key],stable(x['id'])))
            if arm.startswith('explore_'):
                core_n=m-int(m*.2+.5);top=ranking[:core_n]
                picks=top+sorted(ranking[core_n:],key=lambda x:stable(x['id'],'explore'))[:m-core_n]
            else:picks=ranking[:m]
            for x in picks:records[x['id']]['accepted'].append(arm)
            for x in group if arm.startswith('teacher_') else picks:delay(q,x['id'])
    writegz(P/(kind+'_allocation.jsonl.gz'),records.values())
    return {'total':len(r),'warm':warm,'test':len(scored),'arms':arms}
if __name__=='__main__':
    info={kind:timeline(kind) for kind in ('builds','jobs')};(P/'rosters.json').write_text(json.dumps(info,indent=1))
    print('forecasts and fixed-budget allocation logged')

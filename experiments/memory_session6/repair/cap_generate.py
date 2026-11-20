import time
import re
import requests
from common import *
BASE='cap1024/'
def parse(s):
    c=re.fullmatch(r'```(?:python|py)?\s*\n(.*?)\n```',s,re.S|re.I)
    return (c.group(1) if c else s).strip()+'\n'
def prepare():
    check(read('prediction_lock.json')['hashes'])
    items=read('roster.json')['items']; allreq={}
    for r in items:
        for branch in ('note','raw','current'):
            b=read(path(r['id'],branch+'.json')); k=b['call']; orig=read('calls/'+k+'.json.gz')
            assert orig['request']['max_tokens']==416
            status=orig['response']['choices'][0]['finish_reason']
            row=allreq.setdefault(k,{'cohort':r['cohort'],'uses':[],'old_finish':status,'messages_sha':sha(canonical(orig['request']['messages']))})
            assert row['cohort']==r['cohort']
            row['uses'].append([r['id'],branch])
    hits={k for k,v in allreq.items() if v['old_finish']=='length'};controls=set()
    for c in ('primary','replication'):
        for typ in ('note','source'):
            pool=sorted((k for k,r in allreq.items() if r['cohort']==c and k not in hits|controls and ((typ=='note')==any(b=='note' for i,b in r['uses']))),key=lambda k:sha('capcheck6|'+k))
            controls.update(pool[:2]);assert len(pool)>=2
    assert len(controls)==8
    roster={k:dict(allreq[k],role='cap_hit' if k in hits else 'audit_stop') for k in hits|controls}
    order=sorted(roster,key=lambda k:sha('caporder6|'+k))
    save(BASE+'roster.json',{'all_reader_requests':allreq,'planned':roster,'order':order})
    save(BASE+'design_lock.json',dict(created=stamp(),hashes=subset_hash(['prediction_lock.json','scores.json','plus_scores.json','sensitivity_protocol.md','cap_generate.py','cap_grade.py',BASE+'roster.json'])))
    print('prelocked',len(hits),'unique cap hits and',len(controls),'controls',flush=True)
def run():
    check(read(BASE+'design_lock.json')['hashes']); sch=read(BASE+'roster.json'); paths=[]
    for j,k in enumerate(sch['order']):
        n=BASE+'calls/'+k+'.json.gz';pn=BASE+'programs/'+k+'.py'
        orig=read('calls/'+k+'.json.gz');old=orig['request'];b=dict(old,max_tokens=1024)
        assert b.keys()==old.keys() and [t for t in old if old[t]!=b[t]]==['max_tokens']
        assert sha(canonical(b['messages']))==sch['planned'][k]['messages_sha']
        if not (ROOT/n).exists():
            start=stamp();t=time.monotonic()
            for attempt in range(3):
                try:
                    resp=requests.post('http://127.0.0.1:18961/v1/chat/completions',json=b,timeout=500);resp.raise_for_status();break
                except requests.RequestException:
                    if attempt==2:raise
                    time.sleep(2)
            result=resp.json();out=result['choices'][0]['message']['content'].strip()
            oldtext=orig['response']['choices'][0]['message']['content'].strip()
            save(n,dict(original_key=k,new_key=sha(canonical(b)),request=b,response=result,start=start,queue_wall_seconds=time.monotonic()-t,same_old_text=out==oldtext,same_old_prefix=out.startswith(oldtext)))
        response=read(n);s=response['response']['choices'][0]['message']['content'].strip()
        p=ROOT/pn;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(parse(s).encode())
        paths.extend([n,pn])
        print(stamp(),j+1,'/',len(sch['order']),sch['planned'][k]['role'],flush=True)
    save(BASE+'prediction_lock.json',dict(created=stamp(),hashes=subset_hash(paths)))
if __name__=='__main__':
    if not (ROOT/(BASE+'design_lock.json')).exists():prepare()
    run()


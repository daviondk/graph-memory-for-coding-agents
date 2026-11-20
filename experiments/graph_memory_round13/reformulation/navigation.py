"""Open future tool messages only after validating the frozen predictions and predictor."""
import collections,gzip,json
from prefix import D,R12,V,ext,get,save,h,calls,shown,inspect
def verify_lock():
    lock=get('forecast.lock.json')
    assert all(h((D/n).read_bytes())==v for n,v in lock['files'].items())
def main():
    verify_lock()
    rows=get('inputs.json.gz');roster={r['iid']:r for r in get('roster.json')};by=collections.defaultdict(list)
    for r in rows:by[r['iid']].append(r)
    out=[]
    for iid,cut in by.items():
        rec=roster[iid];raw=(V/'benchmark'/rec['file']).read_bytes();assert h(raw)==rec['sha'];steps=list(calls(json.loads(raw)['messages']))
        for r in cut:
            j=r['index'];assert steps[j][2]==r['id'].split('|',1)[1]
            events=[];other_root=0;unseen=0
            for idx,mi,cid,cmd,toolrow in steps[j+1:j+6]:
                rc,text=shown(toolrow)
                if rc!=0:continue
                if not text:unseen+=1;continue
                f=inspect(cmd,text,r['repo'])
                if len(f)!=1:continue
                root,p,kind,lines=f[0]
                if kind=='grep-list':continue
                if root!=r['key']['root']:other_root+=1;continue
                events.append(dict(delta=idx-j,root=root,path=p,kind=kind,command=cmd,call=cid,raw_sha=h(toolrow['extra']['raw_output'].encode()),visible_sha=h(text.encode()),first_nonempty=next((v[:165] for v in lines if v.strip()),'')))
            target=next(iter(events),None);plain=next((a for a in events if a['kind']=='read'),None)
            out.append(dict(id=r['id'],target=target,plain=plain,events=events,following_observed=min(5,len(steps)-1-j),foreign_roots=other_root,empty_success=unseen))
    save('navigation_labels.json.gz',out)
    print('labels',len(out),'target',sum(x['target'] is not None for x in out),'plain',sum(x['plain'] is not None for x in out))
if __name__=='__main__':main()

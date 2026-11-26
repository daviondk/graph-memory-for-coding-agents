"""Independent sparse integer optimizer and audit of paired withdrawals from the portable files."""
from collections import defaultdict
from hashlib import sha256
import gzip,json,math
from pathlib import Path
D=Path(__file__).resolve().parent

def read(name):
    p=D/name;b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)

def sparse(entries,deleted=None):
    allowed=[(i,x) for i,x in enumerate(entries) if x[0]!=deleted];head=[];load=0
    for i,x in allowed:
        if load+x[3]>1024:break
        head.append(i);load+=x[3]
    tail=allowed[len(head):];states={0:(0,0)}
    for i,x in tail:
        for cost,(utility,mask) in tuple(states.items()):
            total=cost+x[3];gain=utility+x[4];choice=mask|(1<<i)
            if load+total>2048:continue
            incumbent=states.get(total)
            if incumbent is None or (gain,-choice)>(incumbent[0],-incumbent[1]):states[total]=(gain,choice)
    _,mask=max(states.values(),key=lambda v:(v[0],-v[1]));return tuple(head+[i for i,_ in tail if mask&(1<<i)]),tuple(head),tail[0][0] if tail else None

def verify():
    manifest=D/'manifest.json'
    if manifest.exists():
        for name,sha in json.loads(manifest.read_bytes())['files'].items():assert sha256((D/name).read_bytes()).hexdigest()==sha,name
    seal=read('plan-seal.json');assert seal['plans']==sha256((D/'plans.json.gz').read_bytes()).hexdigest() and seal['protocol']==sha256((D/'PROTOCOL_RU.md').read_bytes()).hexdigest()
    plans=read('plans.json.gz');obs=read('observations.json.gz');groups=read('results.json')['groups'];main=[];checks=0
    assert len(obs)==3525 and len(plans)==1324 and len({(o['rid'],o['event']) for o in obs})==len(obs)
    for r in obs:
        entries=plans[r['rid']][str(r['event'])];ids,_,barrier=sparse(entries);selected=set(ids);sources=sorted({item[0] for item in entries});guard={entries[i][0] for i in ids};guard.update([entries[barrier][0]] if barrier is not None else [])
        assert len(ids)==r['selected'] and sum(entries[i][3] for i in ids)==r['bytes'] and r['present']==(r['actual'] in sources)
        after={}
        for source in sources:
            result,h,_=sparse(entries,source);changed=result!=ids;safe=source not in guard
            assert r['by_path'][source]==[int(changed),int(safe)]
            assert changed==((source in {entries[i][0] for i in ids}) or not set(h)<=selected)
            after[source]=int(changed);checks+=1
        assert r['actual_changed']==after.get(r['actual'],0) and math.isclose(r['random_changed'],sum(after.values())/len(after) if after else 0.)
        if r['group']=='main' and len(sources)>=2 and r['present']:main.append(r)
    assert len(main)==59 and checks==3101
    issues=defaultdict(list)
    for row in main:issues[row['issue']].append(row['actual_changed']-row['random_changed'])
    delta=sum(sum(v)/len(v) for v in issues.values())/len(issues);assert len(issues)==16 and abs(delta-groups['main']['multi_active']['delta_macro'])<1e-12
    assert [sum(r['actual_safe'] for r in obs if r['present']),sum(r['actual_safe'] for r in obs)]==[6,711]
    print('Verified',len(obs),'actual attempts and',checks,'same-state source withdrawals with a sparse exact solver.')
if __name__=='__main__':verify()

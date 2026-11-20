from collections import defaultdict
import concurrent.futures
from datetime import datetime, timezone
import gzip, hashlib, json, re, sys, time
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'gate'))
from sources import fetch as official, h

def save(name,v):
    path=ROOT/name;data=json.dumps(v,sort_keys=True,separators=(',',':')).encode()
    if path.suffix=='.gz':data=gzip.compress(data,mtime=0)
    if path.exists():assert path.read_bytes()==data,name
    else:path.write_bytes(data)

def main():
    frozen=json.loads(gzip.decompress((ROOT.parent/'gate/features.json.gz').read_bytes()))
    all_prior={v['issue'] for r in frozen if r['cohort'] in ('chronological','linked') for v in r['history']}
    all_targets={r['issue'] for r in frozen if r['cohort'] in ('chronological','linked')}
    experiences=official('Experience',['repo','instance_id','created_at'])
    targets=official('Related',['repo','instance_id','created_at'])
    date_targets={}
    for r in targets:
        date_targets.setdefault(h(r['repo']+'#issue#'+r['instance_id']),r['created_at'])
    save('target_dates_first.json',{k:date_targets[k] for k in sorted(all_targets)})
    entries={};groups=defaultdict(dict)
    for r in experiences:
        repo=r['repo'];sid=r['instance_id'];key=h(repo+'#issue#'+sid)
        if key not in all_prior:continue
        assert re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo)
        pr=int(re.search(r'[-#]([0-9]+)$',sid)[1])
        if pr in groups[repo]:assert groups[repo][pr]==key
        groups[repo][pr]=key
        entries[key]=dict(repo=repo,pr=pr,created_at=r['created_at'],merged_at=None,method=None)
    assert set(entries)==all_prior
    save('roster.json',entries)
    folder=ROOT/'archive';folder.mkdir(exist_ok=True)
    def get(group):
        repo,nums=group
        name='archive/'+repo.replace('/','__')+'.json.gz'
        query=("SELECT number, minIf(toUnixTimestamp(merged_at), toUnixTimestamp(merged_at)>0) AS first_merge, max(toUnixTimestamp(merged_at)) AS last_merge, min(toUnixTimestamp(created_at)) AS first_merged_event, count() AS events FROM github_events WHERE event_type='PullRequestEvent' AND repo_name='"+
               repo+"' AND action='closed' AND (merged=1 OR toUnixTimestamp(merged_at)>0) AND number IN ("+','.join(map(str,sorted(nums)))+") GROUP BY number ORDER BY number FORMAT JSONEachRow")
        if (ROOT/name).exists():
            response=json.loads(gzip.decompress((ROOT/name).read_bytes()))
            assert response['query']==query
        else:
            for k in range(3):
                try:
                    rr=requests.get('https://play.clickhouse.com/',params={'user':'play','query':query},timeout=55)
                    rr.raise_for_status()
                    response=dict(query=query,lines=[json.loads(x) for x in rr.text.splitlines() if x.strip()])
                    save(name,response);break
                except (ValueError,requests.RequestException):
                    if k==2:raise
                    time.sleep(1.5*(k+1))
        for r in response['lines']:
            pr=int(r['number']);v=entries[nums[pr]]
            first,last=int(r['first_merge']),int(r['last_merge'])
            if first==last and first>0:
                value=last;method='merged_at'
            elif not first and not last:
                value=int(r['first_merged_event']);method='merged_close_event_upper_bound'
            else:continue
            v.update(merged_at=datetime.fromtimestamp(value,timezone.utc).isoformat(),method=method)
        print(repo,len(response['lines']),'/',len(nums),flush=True)
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        list(pool.map(get,sorted(groups.items())))
    save('history_times.json',entries)
    print('history',len(entries),'dates',sum(r['merged_at'] is not None for r in entries.values()))
if __name__=='__main__':main()

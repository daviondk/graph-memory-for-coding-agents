"""Complete known timestamp gaps and check an outcome-blind sample against canonical public PR records."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import requests

ROOT=Path(__file__).resolve().parent
def date(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')) if value else None
def sha(x):
    return hashlib.sha256(x.encode()).hexdigest()
def main():
    rr=ROOT/'rest';rr.mkdir(exist_ok=True)
    old=json.loads((ROOT/'history_times.json').read_bytes())
    missing=sorted(k for k,v in old.items() if not v['merged_at'])
    sample=sorted((k for k,v in old.items() if v['merged_at']),key=lambda k:sha('s6-api-audit|'+k))[:6]
    plan=missing+sample
    def fetch(k):
        path=rr/(k+'.json')
        if path.exists():return
        src=old[k];url=f"https://api.github.com/repos/{src['repo']}/pulls/{src['pr']}"
        for i in range(3):
            response=requests.get(url,timeout=18)
            if response.status_code in (200,403,404,429):break
            time.sleep(1+i)
        item={'url':url,'status':response.status_code}
        if response.ok:
            v=response.json()
            assert int(v['number'])==src['pr']
            item.update(number=v['number'],base_repo=v['base']['repo']['full_name'],created_at=v['created_at'],merged_at=v['merged_at'],closed_at=v['closed_at'],merge_commit_sha=v['merge_commit_sha'])
        path.write_text(json.dumps(item,indent=2),encoding='utf8')
    with ThreadPoolExecutor(3) as pool:list(pool.map(fetch,plan))
    confirmed=0;conflicts=0;closed_unmerged=0
    for k in plan:
        item=json.loads((rr/(k+'.json')).read_bytes());prev=old[k]['merged_at']
        if item['status']!=200:continue
        actual=date(item['merged_at']);before=date(prev)
        if k in sample:
            if before==actual:confirmed+=1
            elif old[k]['method']=='merged_close_event_upper_bound' and actual and actual<=before:confirmed+=1
            else:conflicts+=1
        if actual:
            old[k].update(merged_at=actual.isoformat(),method='github_rest')
        else:
            old[k].update(merged_at=None,method='github_not_merged')
            closed_unmerged+=1
    output={'selected':len(old),'archive_available':len(old)-len(missing),'api_gap_queries':len(missing),'api_validation_queries':len(sample),'validation_agrees':confirmed,'validation_differs':conflicts,'api_nonmerged':closed_unmerged,'available':sum(v['merged_at'] is not None for v in old.values()),'http_status_counts':{str(s):sum(json.loads((rr/(k+'.json')).read_bytes())['status']==s for k in plan) for s in sorted({json.loads((rr/(k+'.json')).read_bytes())['status'] for k in plan})}}
    for name,v in [('verified_times.json',old),('results.json',output)]:
        path=ROOT/name
        if path.exists():assert json.loads(path.read_bytes())==v
        else:path.write_text(json.dumps(v,indent=1),encoding='utf8')
    print(output)
if __name__=='__main__':main()

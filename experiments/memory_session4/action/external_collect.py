import hashlib,itertools,json,urllib.request,urllib.error,time
from collections import defaultdict
from pathlib import Path
P=Path(__file__).resolve().parent/'github'
REPOS='pytorch/pytorch pandas-dev/pandas numpy/numpy scipy/scipy python/cpython pytest-dev/pytest django/django nodejs/node apache/spark openjdk/jdk dotnet/runtime kubernetes/kubernetes'.split()
KEYS='id run_attempt status conclusion head_sha workflow_id event created_at run_started_at updated_at'.split()
def h(x):return hashlib.sha256(x.encode()).hexdigest()
def obtain(key,url):
    p=P/(key+'.json')
    if p.exists():return json.loads(p.read_bytes())
    req=urllib.request.Request(url,headers={'User-Agent':'CodexResearch-retry-study','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    for i in range(3):
        try:
            with urllib.request.urlopen(req,timeout=40) as response:
                b=response.read();remaining=response.headers.get('X-RateLimit-Remaining')
                j=json.loads(b); arr=j['workflow_runs'] if 'workflow_runs' in j else [j]
                d={'url':url,'sha256_source':hashlib.sha256(b).hexdigest(),'status':200,'rate_remaining':remaining,'rows':[{k:x.get(k) for k in KEYS} for x in arr]}
                break
        except urllib.error.HTTPError as e:
            d={'url':url,'status':e.code,'reason':e.reason,'rows':[]};break
        except OSError as e:
            if i==2:d={'url':url,'status':0,'reason':str(e),'rows':[]}
            else:time.sleep(1)
    p.write_text(json.dumps(d,separators=(',',':')));return d
def main():
    P.mkdir(exist_ok=True);bins={}
    for r in REPOS:
        u='https://api.github.com/repos/'+r+'/actions/runs?per_page=100&created=2026-10-01..2026-11-15'
        d=obtain('index-'+r.replace('/','_'),u);c=[x for x in d['rows'] if x['run_attempt']==2 and x['status']=='completed']
        bins[r]=sorted(c,key=lambda x:h(str(x['id'])))
    roster=[(r,v) for group in itertools.zip_longest(*(bins[r] for r in REPOS)) for r,v in zip(REPOS,group) if v is not None][:32]
    (P/'roster.json').write_text(json.dumps([[r,x['id']] for r,x in roster],indent=1))
    for r,x in roster:
        u=f"https://api.github.com/repos/{r}/actions/runs/{x['id']}/attempts/1"
        d=obtain('attempt-'+str(x['id']),u)
        if d['status'] in (403,429):break
    print('raw index and retrieved metadata stored')
if __name__=='__main__':main()

"""Read actual old->merge paths only after ranking is sealed. Separate scratch mirrors on D."""
import collections,concurrent.futures,json,os,re,subprocess,time,urllib.request
from pathlib import Path
from prefix import D,R12,get,save,h
from navigation import verify_lock
CACHE=Path('D:/CodexResearch/x20-round13-reformulation-objects')
def meta(t):
    iid,repo=t;dest=D/'pr_refs'/(iid+'.json')
    if dest.exists():return json.loads(dest.read_bytes())
    num=iid.rsplit('-',1)[1];url=f'https://github.com/{repo}/pull/{num}';row=dict(iid=iid,repo=repo,url=url,status='unavailable')
    for j in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 research Git revision reader'}),timeout=23) as fp:html=fp.read()
            page=html.decode();ids=set(re.findall(r'"mergeCommitSha"\s*:\s*"([a-f0-9]{40})"',page));explicit=set(re.findall(r'merged commit\s*<a[^>]+href="[^"]*/commit/([a-f0-9]{40})"',page))
            if len(ids)!=1 or (explicit and explicit!=ids) or not ('State--merged' in page or '>Merged</' in page or explicit):raise ValueError('no merged SHA')
            row.update(status='ok',merge=ids.pop(),html_sha=h(html));break
        except (OSError,ValueError) as e:
            row['error']=str(e)[:170]
            if j<2:time.sleep(.8*(j+1))
    save('pr_refs/'+iid+'.json',row);return row
def production(p):
    ps=p.lower().split('/')
    return p.endswith('.py') and not set(ps[:-1])&{'test','tests','testing','docs','doc','example','examples'} and not ps[-1].startswith('test_') and not ps[-1].endswith('_test.py') and ps[-1]!='conftest.py'
def fetch(group):
    repo,rows=group
    root=CACHE/(repo.replace('/','__')+'.git');root.parent.mkdir(parents=True,exist_ok=True)
    env={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1"}
    def git(*args):
        z=subprocess.run(['git','-C',str(root),*args],env=env,capture_output=True,timeout=220)
        if z.returncode:raise RuntimeError(z.stderr.decode(errors='replace')[-250:])
        return z.stdout
    if not root.exists():
        subprocess.run(['git','init','--bare',str(root)],capture_output=True,check=True);git('remote','add','origin','https://github.com/'+repo+'.git')
    # No blob needed to compute --name-status without similarity detection.
    ids=sorted({r['merge'] for r in rows});args=('fetch','--no-tags','--depth=2','--filter=blob:none','origin',*ids)
    try:git(*args)
    except (OSError,RuntimeError):git(*args)
    for r in rows:
        c=r['merge'];parents=git('show','-s','--format=%P',c).decode().split();p=parents[0]
        a,b=[int(git('show','-s','--format=%ct',x).strip()) for x in (p,c)];r.update(parent=p,old_time=a,new_time=b,strict=r['base']==p and a<=b)
        z=git('diff','--name-status','-z','--no-renames',p,c).split(b'\0');old=[];allpy=[];added=[]
        for status,path in zip(z[:-1:2],z[1::2]):
            name=path.decode('utf8','surrogateescape')
            if not name.endswith('.py'):continue
            allpy.append(name)
            if status in (b'M',b'D',b'T'):old.append(name)
            if status==b'A':added.append(name)
        r.update(existing_py=sorted(old),prod=sorted(q for q in old if production(q)),all_py=sorted(allpy),added_py=sorted(added))
    print(repo,len(rows),flush=True);return rows
def main():
    verify_lock();(D/'pr_refs').mkdir(exist_ok=True)
    native={r['iid']:r for r in json.loads((R12/'pr_metadata.json').read_bytes())}
    original=json.loads((R12/'task_meta_panel.json').read_bytes())
    pairs=sorted(set((r['iid'],r['repo']) for r in get('inputs.json.gz')))
    for iid,repo in pairs:
        if iid in native:save('pr_refs/'+iid+'.json',{k:v for k,v in native[iid].items() if k in ('iid','repo','url','merge','html_sha','status')})
    with concurrent.futures.ThreadPoolExecutor(5) as pool:rec=list(pool.map(meta,pairs))
    by=collections.defaultdict(list)
    for r in rec:
        if r['status']=='ok':r['base']=original[r['iid']]['base_commit'];by[r['repo']].append(r)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        for _ in pool.map(fetch,by.items()):pass
    save('patch_labels.json.gz',rec)
    print('total',len(rec),'strict',sum(r.get('strict',False) for r in rec))
if __name__=='__main__':main()

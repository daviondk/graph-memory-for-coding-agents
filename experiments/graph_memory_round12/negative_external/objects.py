"""Materialise full immutable Git trees for offline evaluation and timing. No checkout and no repo code execution."""
import collections, concurrent.futures, os, re, subprocess, time
from pathlib import Path
from extract import D,get,save,h
ENV={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_OPTIONAL_LOCKS":"0","GIT_LFS_SKIP_SMUDGE":"1","GIT_NO_LAZY_FETCH":"1","LC_ALL":"C"}
CACHE=Path("D:/CodexResearch/x20-round12-negative-objects")
def local(repo):return CACHE/(repo.replace("/","__")+".git")
def git(repo,*cmd,timeout=150,check=True,input=None):
    return subprocess.run(["git","-C",str(local(repo)),*cmd],capture_output=True,env=ENV,timeout=timeout,check=check,input=input)
def fetch(group):
    repo,items=group;bare=local(repo);bare.parent.mkdir(exist_ok=True)
    if not bare.exists():
        subprocess.run(["git","init","--bare",str(bare)],capture_output=True,check=True)
        git(repo,"remote","add","origin","https://github.com/"+repo+".git")
    shas=sorted({r["merge"] for r in items});start=time.perf_counter()
    args=["fetch","--no-tags","--depth=2","origin",*shas]
    p=git(repo,*args,timeout=500,check=False)
    if p.returncode:
        p=git(repo,*args,timeout=500,check=False)
    receipt={'repo':repo,'requested':shas,'fetch_rc':p.returncode,'stderr':p.stderr.decode(errors='replace')[-1800:],'seconds':round(time.perf_counter()-start,4)}
    if p.returncode==0:
        receipt['commits']={}
        for m in shas:
            body=git(repo,"show","-s","--format=%H%n%P%n%ct%n%T",m).stdout.decode().splitlines()
            parent=body[1].split()[0]
            before=git(repo,"show","-s","--format=%ct%n%T",parent).stdout.decode().splitlines()
            receipt['commits'][m]={'parents':body[1].split(),'new_time':int(body[2]),'old_time':int(before[0]),'new_tree':body[3],'old_tree':before[1]}
    dest=D/'git_traces';dest.mkdir(exist_ok=True)
    save('git_traces/'+repo.replace('/','__')+'.json',receipt)
    print(repo,p.returncode,round(receipt['seconds'],1),flush=True)
    return receipt
if __name__=="__main__":
    groups=collections.defaultdict(list)
    for r in get(D/'pr_metadata.json'):
        if r['status']=='ok':groups[r['repo']].append(r)
    with concurrent.futures.ThreadPoolExecutor(5) as ex:allr=list(ex.map(fetch,sorted(groups.items())))
    save('objects.json',allr)

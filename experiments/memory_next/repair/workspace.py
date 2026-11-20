"""Offline Linux worktrees exported from the pinned official image base, with a new single-commit Git."""
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path

HERE=Path(__file__).resolve().parent
CACHE=Path('D:/CodexResearch/x20-repair-checkouts')
WSL=['wsl.exe','-d','CodexX20MSR','--exec','docker']

def docker(args,check=True,timeout=180):
    return subprocess.run(WSL+args,check=check,timeout=timeout,capture_output=True)

def prepare(row):
    CACHE.mkdir(exist_ok=True,parents=True)
    f=CACHE/(row['commit']+'.tar')
    raw=docker(['image','inspect',row['image']])
    image=json.loads(raw.stdout)[0]
    image_id=image['Id']
    head=docker(['run','--rm','--network','none','--entrypoint','git',image_id,'-C','/testbed','rev-parse','HEAD']).stdout.decode().strip()
    assert head==row['commit'],(row['id'],head)
    if not f.exists():
        tmp=f.with_suffix('.partial')
        with tmp.open('wb') as out:
            subprocess.run(WSL+['run','--rm','--network','none','--entrypoint','git',image_id,'-C','/testbed','archive','--format=tar',head],stdout=out,check=True,timeout=180)
        tmp.replace(f)
    return {'image_id':image_id,'repo_digests':image.get('RepoDigests'),'head':head,'archive':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}

def create(row,proof):
    name='nextrepair-'+uuid.uuid4().hex[:14]
    docker(['run','-d','--name',name,'--network','none','--pids-limit','192','--memory','2500m','--tmpfs','/testbed:rw,exec,size=384m','--entrypoint','sleep',proof['image_id'],'infinity'])
    try:
        arch=Path(proof['archive'])
        path='/mnt/d/'+arch.as_posix()[3:]
        docker(['cp',path,name+':/tmp/source.tar'])
        script=('set -eu; cd /testbed; tar -xf /tmp/source.tar; rm /tmp/source.tar; '
                'git init -q; git -c core.autocrlf=false add -f .; '
                'git -c user.name=benchmark -c user.email=b@localhost commit -qm baseline; '
                'chown -R 1000:1000 /testbed; mkdir -p /tmp/agent-home; chown 1000:1000 /tmp/agent-home')
        docker(['exec','--user','0',name,'bash','-c',script])
        return name
    except Exception:
        docker(['rm','-f',name],check=False)
        raise

def shell(name,cmd):
    return docker(['exec','--user','1000:1000','-e','HOME=/tmp/agent-home','-w','/testbed',name,'timeout','-k','3','75','bash','-c',cmd],check=False,timeout=90)

def patch(name):
    run=shell(name,'git -c core.autocrlf=false add -N . && git diff --no-ext-diff --binary HEAD')
    if run.returncode:raise RuntimeError(run.stderr.decode(errors='replace'))
    return run.stdout

if __name__=='__main__':
    proofs={r['id']:prepare(r) for r in json.loads((HERE/'inputs.json').read_text(encoding='utf8'))}
    (HERE/'images.json').write_text(json.dumps(proofs,indent=2),encoding='utf8')
    r=json.loads((HERE/'inputs.json').read_text(encoding='utf8'))[0]
    n=create(r,proofs[r['id']])
    try:
        assert shell(n,'git rev-list --count HEAD').stdout.strip()==b'1'
        assert patch(n)==b''
        print('Offline checkout, single commit, clean initial diff, four image digests verified.')
    finally:docker(['rm','-f',n],check=False)


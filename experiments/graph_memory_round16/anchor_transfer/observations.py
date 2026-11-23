"""Recover literal prior editor output and validate on the immutable benchmark checkout."""
import collections
import concurrent.futures
import hashlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

from cohort import CACHE, MODELS, ROOT, S3, load, save, sha

HEADER = re.compile(r"^\[File: ([^\n]+?) \((\d+) lines? total\)\]\r?$", re.M)
LINE = re.compile(r"^(\d+):(.*)$")
COMMAND = re.compile(r"^(?:open(?:\s+[^\n]+)?|goto\s+\d+|scroll_down|scroll_up)$")
def fetch(uri, file):
    if file.is_file(): return file.read_bytes()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(uri,headers={'User-Agent':'agent-memory-research'}),timeout=30) as res:
                data=res.read()
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(data)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code==404: return None
            if exc.code not in (429, 500, 502, 503, 504) or attempt==3: raise
        except OSError:
            if attempt==3: raise
        time.sleep(1+attempt)
def read_traj(args):
    iid, model, task = args
    obj=task['trajectories'][model]
    raw=fetch(S3+obj['key'], CACHE/'trajectories'/model/(iid+'.json'))
    assert raw and hashlib.md5(raw).hexdigest() == obj['etag'], (iid,model)
    from json import loads
    stream=loads(raw)
    views=[]
    eligible_actions=0
    repository_folder=task['repo'].replace('/','__')
    for index,step in enumerate(stream['trajectory']):
        action=(step.get('action') or '').strip()
        if not COMMAND.fullmatch(action): continue
        eligible_actions+=1
        obs=step.get('observation') or ''
        head=HEADER.search(obs)
        if not head:continue
        path=PurePosixPath(head[1])
        if len(path.parts)<3 or path.parts[0]!='/' or path.parts[1] not in (repository_folder,'testbed') or path.suffix!='.py': continue
        relative=PurePosixPath(*path.parts[2:])
        if '..' in relative.parts:continue
        lines=[]
        for line in obs[head.end():].splitlines():
            match=LINE.fullmatch(line)
            if match: lines.append((int(match[1]),match[2]))
        if not lines:continue
        assert all(b[0]==a[0]+1 for a,b in zip(lines,lines[1:])),(iid,model)
        views.append(dict(index=index,action=action,path=str(relative),lines=lines,printed_lines=int(head[2])))
        if len(views)>=6:break
    return dict(instance_id=iid,repo=task['repo'],source=model,base_commit=task['base_commit'],views=views,
        eligible_commands_through_cut=eligible_actions,trajectory_sha256=sha(raw),trajectory_bytes=len(raw))
def raw_url(repo,base,path):
    return 'https://raw.githubusercontent.com/'+repo+'/'+base+'/'+urllib.parse.quote(path,safe='/')
def materialize(uri):
    data=fetch(uri,CACHE/'base'/sha(uri.encode()))
    if data is None: return None
    try:
        return data.decode('utf8').splitlines(),sha(data)
    except UnicodeDecodeError:
        return [],sha(data)
def main():
    for key,h in load(ROOT/'cohort.lock.json').items():assert sha((ROOT/key).read_bytes())==h
    tasks=load(ROOT/'cohort.json')['tasks']
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        rows=list(pool.map(read_traj,[(i,m,t) for i,t in tasks.items() for m in MODELS]))
        uris=sorted({raw_url(r['repo'],r['base_commit'],v['path']) for r in rows for v in r['views']})
        data=dict(zip(uris,pool.map(materialize,uris)))
    repro=[]
    for row in rows:
        for v in row['views']:
            uri=raw_url(row['repo'],row['base_commit'],v['path'])
            content=data[uri]
            v['base_status']='absent' if content is None else 'match' if all(1<=n<=len(content[0]) and line==content[0][n-1] for n,line in v['lines']) else 'different'
            v['base_blob_sha256']=content[1] if content else None
            if v['base_status']!='match':v['lines']=[]
        repro.append({**{k:row[k] for k in ('instance_id','source','repo','base_commit')},
                      'views3':[{'path':v['path'],'lines':v['lines'],'event':v['index']} for v in row['views'][:3] if v['base_status']=='match'],
                      'views6':[{'path':v['path'],'lines':v['lines'],'event':v['index']} for v in row['views'][:6] if v['base_status']=='match']})
    save('observations.json.gz',rows)
    save('input-priors.json.gz',repro)
    save('inputs.lock.json',{n:sha((ROOT/n).read_bytes()) for n in ('cohort.lock.json','observations.py','observations.json.gz','input-priors.json.gz')})
    print(len(rows),len(uris),sum(r['trajectory_bytes'] for r in rows),collections.Counter(v['base_status'] for r in rows for v in r['views']))
if __name__=='__main__':
    main()

"""Freeze the cache content before the next edit is read."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
METHODS=['recency','confirmation','diversity','protect','frequency']
def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,v):
    path=ROOT/name;buf=encode(v)
    if path.suffix=='.gz':buf=gzip.compress(buf,mtime=0)
    if path.exists():assert path.read_bytes()==buf,name
    else:path.write_bytes(buf)

def update(cache, files, step, method, cap):
    # Each resident record stores last use, observed multiplicity while resident, and directory.
    pool=dict(cache)
    for path,folder in files.items():
        pool[path]=(step,1+(cache[path][1] if path in cache else 0),folder)
    if method=='recency':
        order=sorted(pool,key=lambda p:(-pool[p][0],p))
    elif method=='frequency':
        order=sorted(pool,key=lambda p:(-pool[p][1],-pool[p][0],p))
    else:
        order=sorted(pool,key=lambda p:(-pool[p][0],-int(p in cache),p))
    if method=='protect':
        steady=[p for p in order if p in cache and pool[p][1]>=2]
        if steady:
            best=min(steady,key=lambda p:(-pool[p][1],-pool[p][0],p))
            order=[best]+[p for p in order if p!=best]
    if method=='diversity':
        seen=set();head=[];tail=[]
        for p in order:
            directory=pool[p][2]
            if directory in seen:tail.append(p)
            else:head.append(p);seen.add(directory)
        order=head+tail
    return {p:pool[p] for p in order[:cap]}

def main():
    proj=json.loads(gzip.decompress((ROOT/'projection.json.gz').read_bytes()))
    options={};positions=0
    for row in proj:
        steps=row['steps']
        for t in range(2,len(steps)):
            before=steps[:t];target=steps[t];tag=(row['repo'],target['issue'])
            if not all(s['allowed'] and s['files'] for s in steps[:t+1]) or any(s['issue']==target['issue'] for s in before):
                continue
            rank=sha((row['sequence']+'/'+str(t)).encode());positions+=1
            if tag not in options or rank<options[tag][0]:options[tag]=(rank,row,t)
    out=[];gold=[]
    for (repo,issue),(_,row,t) in sorted(options.items()):
        history=row['steps'][:t]
        rec=dict(repo=repo,issue=issue,sequence=row['sequence'],previous_tasks=t,policies={},seen=sorted({p for s in history for p in s['files']}))
        for cap in [1,3,8]:
            for method in METHODS:
                cache={};added=0
                for i,old in enumerate(history):
                    nxt=update(cache,old['files'],i,method,cap)
                    added+=len(nxt.keys()-cache.keys());cache=nxt
                rec['policies'][f'{cap}/{method}']={'keys':sorted(cache),'added':added}
        out.append(rec)
        gold.append(dict(issue=issue,repo=repo,keys=sorted(row['steps'][t]['files'])))
    save('decisions.json.gz',out)
    save('decision_lock.json',{'n':len(out),'eligible_positions':positions,'hashes':{n:sha((ROOT/n).read_bytes()) for n in ['PROTOCOL.md','project.py','projection.json.gz','retain.py','decisions.json.gz']}})
    save('gold.json.gz',gold)
    print('frozen',len(out),'distinct targets')
if __name__=='__main__':main()

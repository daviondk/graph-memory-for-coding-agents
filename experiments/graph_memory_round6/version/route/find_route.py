import base64
import collections
import gzip
import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import replay
from replay import old

ARMS=('recent','edited','combined')
STOP=set('and the for this that with from are can should would be have was when not all code test file here issue python return class self as import this has only none does error object true false its into out after then been but where which line following github https org com use run new you will they example case one see get how had expected actual result version now some than used fix tests'.split())


def tokens(text):
    return {w.lower() for w in re.findall(r'[A-Za-z_][A-Za-z_0-9]{2,}',text)}-STOP


def propose(issue,blob):
    t,state,meta,_,last=old.prior.materialize(old.decode(blob[1:]))
    query=tokens(issue[:9000])
    windows=[];df=collections.Counter()
    for path,values in sorted(state['rebase'].items()):
        for group in old.anchor.groups(values):
            for pos in range(0,len(group),10):
                ns=group[pos:pos+10]
                lex=query & tokens('\n'.join(values[n][0] for n in ns))
                name=query & tokens(path.replace('/',' ').replace('.',' '))
                df.update(lex|name)
                midpoint=(ns[0]+ns[-1])/2
                recent=(-max(values[n][1] for n in ns),-meta['paths'][path],abs(midpoint-meta['center'][path]),path,ns[0])
                edited=meta['edited'].get(path,-1)
                windows.append(dict(path=path,lo=ns[0],hi=ns[-1],lex=lex,name=name,recent=recent,edited=edited,visits=meta['visits'][path]))
    N=len(windows)
    def idf(words):
        return sum(math.log((N+1)/(df[w]+.5)) for w in sorted(words))
    for z in windows:
        z['overlap']=idf(z['lex'])+2*idf(z['name'])
    recent=sorted(range(N),key=lambda i:windows[i]['recent'])
    edited=sorted(recent,key=lambda i:-windows[i]['edited'])
    lexical=sorted(recent,key=lambda i:-windows[i]['overlap'])
    rr={i:j for j,i in enumerate(recent,1)}
    er={i:j for j,i in enumerate(edited,1)}
    lr={i:j for j,i in enumerate(lexical,1)}
    def fusion(i):
        z=windows[i]
        score=(1+.15*min(1,math.log2(1+z['visits'])/4))/(4+rr[i])
        if z['overlap']:score+=1.2/(4+lr[i])
        if z['edited']>=0: score+=.35/(4+er[i])
        return -score
    combined=sorted(recent,key=fusion)
    return {a:[[windows[i]['path'],windows[i]['lo'],windows[i]['hi']] for i in order[:3]] for a,order in zip(ARMS,[recent,edited,combined])},N


def lock(name,files):
    (HERE/name).write_text(json.dumps(dict(utc=old.stamp(),files={os.path.relpath(p,HERE).replace('\\','/'):replay.digest(p) for p in files}),indent=1))


def main():
    assert not (HERE/'answer_lock.json').exists()
    replay.check('state_lock.json')
    lock('method_lock.json',[HERE/f for f in ['find_route.py','route_score.py','PROTOCOL_RU.md']]+[HERE.parent/'state_lock.json',HERE.parent/'method_lock.json',HERE.parent/'score.py'])
    with gzip.open(HERE/'routes.jsonl.gz','wt',encoding='utf8') as out:
        for panel,k in replay.jobs():
            src,_=replay.inputs(panel,k)
            problems={q['instance']:q['issue'] for q in old.rr(src)}
            for iid,t,snap,_ in old.rr(HERE.parent/f'states_{panel}_{k}.gz'):
                if t%4: continue
                start=time.perf_counter_ns()
                proposals,n=propose(problems[iid],base64.b64decode(snap['r5']))
                elapsed=time.perf_counter_ns()-start
                old.write(out,[panel,iid,t,n,proposals,elapsed])
    lock('answer_lock.json',[HERE/'routes.jsonl.gz',HERE/'method_lock.json'])


if __name__=='__main__':main()

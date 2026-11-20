"""New panel only. Reuse frozen observation parser and exact prior read, every original eligible cut."""
import base64
import gzip
import json
from prepare import HERE, emit,matched_inputs,r5,rows,sha,stable

VERSION=HERE.parent/'version'
OUT=HERE/'external'


def main():
    raw=VERSION/'external'
    seal=json.loads((raw/'sources_lock.json').read_bytes())
    assert all(sha(raw/k)==v for k,v in seal['files'].items())
    assert sha(VERSION/'states_external_0.gz')==json.loads((VERSION/'state_lock.json').read_bytes())['files']['states_external_0.gz']
    gold_prior={(r['id'],r['cut']):r for r in rows(VERSION/'block_outcomes.jsonl.gz') if r['panel']=='external'}
    states=iter(rows(VERSION/'states_external_0.gz'))
    OUT.mkdir(exist_ok=False)
    scores=0
    marks=0
    kimis={r['id'] for r in rows(HERE/'stream.jsonl.gz')}
    with (gzip.open(OUT/'stream.jsonl.gz','wt',encoding='utf8') as ss,
          gzip.open(OUT/'queries.jsonl.gz','wt',encoding='utf8') as qq,
          gzip.open(OUT/'answers.jsonl.gz','wt',encoding='utf8') as aa,
          gzip.open(OUT/'graph.jsonl.gz','wt',encoding='utf8') as gg):
        for q,(iid,terms) in zip(rows(raw/'source.gz'),rows(raw/'terminal.gz'),strict=True):
            assert q['instance']==iid and iid not in kimis
            events=matched_inputs(q,terms)
            emit(ss,dict(id=iid,repo=q['official_repo'],events=events))
            blobs={}
            tests=[]
            controls=[]
            for step,event in enumerate(events,1):
                i,t,b,cost=next(states)
                assert (i,t)==(iid,step)
                if t%4 or t==len(events):
                    continue
                blobs[t]=b
                a,obs=r5.anchor.future_check(q['events'],t)
                if a:
                    path=r5.anchor.rel(a.get('path'))
                    if r5.anchor.success(a.get('command'),path,obs) and (target:=r5.anchor.invert(a,obs)):
                        lo,ls=target
                        tests.append(('edit',t,path,lo,ls,None))
                recent=set()
                for ev in reversed(events[:t]):
                    if ev['rev']!=event['rev']:
                        break
                    for path,spans in ev['files'].items():
                        if path in recent:
                            continue
                        recent.add(path)
                        if ev['step']==t:
                            continue
                        for start,lines in spans:
                            if len(lines)<3:
                                continue
                            half=(len(lines)-3)//2
                            ls=lines[half:half+3]
                            import re
                            if not any(len(re.sub(r'\W','',s))>=8 for s in ls):
                                continue
                            controls.append((stable([iid,t,path,start+half,ev['step']]),('control',t,path,start+half,ls,ev['step'])))
            if controls:
                tests.append(min(controls,key=lambda v:v[0])[1])
            for kind,t,path,lo,ls,source in tests:
                k=f'{iid}/{t}/{kind}'
                emit(qq,dict(key=k,id=iid,repo=q['official_repo'],kind=kind,t=t,path=path,lo=lo,n=len(ls),source=source))
                emit(aa,[k,ls])
                predictions={}
                for alias,field in [('address','r5'),('lru_address','lru')]:
                    value=base64.b64decode(blobs[t][field])
                    assert len(value)<=4096
                    state=r5.bound.decode(value[1:])
                    assert state[1]==t
                    table=r5.bound.prior.materialize(state)[1]['rebase'].get(path,{})
                    predictions[alias]=[table.get(n,(None,))[0] for n in range(lo,lo+len(ls))]
                    if kind=='edit':
                        prior=gold_prior[iid,t]
                        assert (prior['path'],prior['line'],prior['n'])==(path,lo,len(ls))
                        assert prior['out'][field]['full']==int(predictions[alias]==ls)
                emit(gg,[k,predictions])
                if kind=='edit':
                    scores+=predictions['address']==ls
                    marks+=1
    assert next(states,None) is None and (scores,marks)==(122,186)
    print('original frozen graph readout',scores,marks,'all rows and controls',
          sum(1 for _ in rows(OUT/'queries.jsonl.gz')))


if __name__=='__main__':
    main()

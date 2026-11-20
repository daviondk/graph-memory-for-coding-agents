"""Evaluate only coordinates recovered from the public rendered MemTrace frame."""
from collections import Counter, defaultdict
from pathlib import Path
from hashlib import sha256
import gzip
import json
import re
import sys
import numpy as np

HERE=Path(__file__).resolve().parent


def read(name):
    with gzip.open(HERE/name,'rt',encoding='utf8') as fp:
        return [json.loads(line) for line in fp]


def decode_output(response,path,lo,width):
    if not response:
        return [None]*width
    # Consume only the delivered envelope. Capturing additional slice internals
    # here would grant the evaluator access to bytes the agent never saw.
    frame=json.loads(response.split('\n',2)[2].rsplit('\n',1)[0])
    found=defaultdict(list)
    def walk(item, inherited='', age=-1):
        if isinstance(item,list):
            for child in item:
                walk(child,inherited,age)
        elif isinstance(item,dict):
            location=item.get('path',inherited)
            age=item.get('observed_step',age)
            if location==path:
                bounds=item.get('line_range',[])
                if isinstance(bounds,str):
                    match=re.fullmatch(r'\s*(\d+)\s*->\s*(\d+)\s*',bounds)
                    bounds=list(map(int,match.groups())) if match else []
                text=item.get('code_excerpt',item.get('code'))
                if isinstance(text,str) and isinstance(bounds,list) and len(bounds)==2 and all(isinstance(v,int) for v in bounds):
                    # Every admitted input fragment includes the true terminal LF.
                    # A truncated last line without its LF is ambiguous and ignored.
                    complete=text.split('\n')[:-1]
                    for off,s in enumerate(complete[:bounds[1]-bounds[0]+1]):
                        found[bounds[0]+off].append((age,s))
            for k,v in item.items():
                if k=='content_json_excerpt' and isinstance(v,str):
                    try: extra=json.loads(v)
                    except (ValueError,TypeError): continue
                    walk(extra,location,age)
                elif isinstance(v,(dict,list)):
                    walk(v,location,age)
    walk(frame)
    answer=[]
    for n in range(lo,lo+width):
        if n not in found:
            answer.append(None)
            continue
        newest=max(age for age,_ in found[n])
        unique={s for age,s in found[n] if age==newest}
        answer.append(unique.pop() if len(unique)==1 else None)
    return answer


def paired(data,a,b):
    groups=defaultdict(lambda:[0,0])
    w=l=0
    for row in data:
        d=row['m'][a]['full']-row['m'][b]['full']
        groups[row['id']][0]+=d
        groups[row['id']][1]+=1
        w+=d>0
        l+=d<0
    arr=np.array(list(groups.values()),dtype=int)
    rng=np.random.default_rng(19112026)
    sample=arr[rng.integers(len(arr),size=(20000,len(arr)))].sum(axis=1)
    ci=np.quantile(sample[:,0]/sample[:,1],[.025,.975])
    distribution={0:1}
    for diff,_ in arr:
        if diff:
            nxt=Counter()
            for value,count in distribution.items():
                nxt[int(value+diff)]+=count
                nxt[int(value-diff)]+=count
            distribution=nxt
    p=sum(v for d,v in distribution.items() if abs(d)>=abs(w-l))/sum(distribution.values())
    return dict(wins=w,losses=l,ties=len(data)-w-l,delta=(w-l)/len(data),ci=ci.tolist(),p=p)


def main():
    locked=json.loads((HERE/'prediction_freeze.json').read_text())
    for name,h in locked['files'].items():
        assert sha256((HERE/name).read_bytes()).hexdigest()==h
    qrows=read('queries.jsonl.gz')
    graph=dict(read('graph.jsonl.gz'))
    ans=dict(read('answers.jsonl.gz'))
    rendered=dict(read('measured/rendered.jsonl.gz'))
    sources={t['id']:t for t in read('stream.jsonl.gz')}
    assert len(qrows)==len(ans)==len(graph)==len(rendered)==278
    data=[]
    for q in qrows:
        k=q['key']
        expected=ans[k]
        assert len(expected)==q['n']
        pred=graph[k].copy()
        diagnostic={}
        for mode,response in rendered[k].items():
            pred[mode]=decode_output(response['rendered'],q['path'],q['lo'],q['n'])
            diagnostic[mode]={kk:vv for kk,vv in response.items() if kk!='rendered'}
            diagnostic[mode]['delivered_bytes']=len(response['rendered'].encode())
        direct=rendered[k]['direct']
        observed={}
        if direct.get('source') is not None:
            step=direct['source']
            assert step<=q['t']
            ev=sources[q['id']]['events'][step-1]
            assert ev['step']==step and direct['source_revision']=='rev-'+str(ev['rev'])
            for lo,lines in ev['files'][q['path']]:
                observed.update({lo+i:s for i,s in enumerate(lines)})
        pred['source_oracle']=[observed.get(n) for n in range(q['lo'],q['lo']+q['n'])]
        measured={}
        for method,ls in pred.items():
            assert len(ls)==q['n']
            matches=[x==y for x,y in zip(ls,expected,strict=True)]
            measured[method]=dict(full=int(all(matches)),line_fraction=sum(matches)/len(matches),
                                  wrong=sum(x is not None and x!=y for x,y in zip(ls,expected,strict=True)),
                                  available=sum(x is not None for x in ls))
        data.append({**q,'m':measured,'diag':diagnostic,'predictions':pred})
    with gzip.open(HERE/'paired.jsonl.gz','wt',encoding='utf8') as f:
        for row in data:
            f.write(json.dumps(row,ensure_ascii=True)+'\n')
    out={}
    for kind in ('edit','control'):
        selected=[r for r in data if r['kind']==kind]
        methods={}
        for m in selected[0]['m']:
            methods[m]=dict(full=sum(r['m'][m]['full'] for r in selected),
                            line_fraction=np.mean([r['m'][m]['line_fraction'] for r in selected]),
                            wrong_returned_lines=sum(r['m'][m]['wrong'] for r in selected),
                            present_returned_lines=sum(r['m'][m]['available'] for r in selected))
        pairs={f'{a}-{b}':paired(selected,a,b) for a,b in (
            ('address','direct'),('address','exact'),('direct','exact'),('address','source_oracle'),('direct','source_oracle'))}
        reads={m:dict(status=dict(Counter(r['diag'][m]['status'] for r in selected)),
                      mean_delivered_bytes=np.mean([r['diag'][m]['delivered_bytes'] for r in selected]),
                      pages=sum(r['diag'][m]['pages_read'] for r in selected)) for m in ('exact','direct')}
        repos={repo:{m:sum(r['m'][m]['full'] for r in selected if r['repo']==repo) for m in methods}
               | {'queries':sum(r['repo']==repo for r in selected)} for repo in sorted({r['repo'] for r in selected})}
        out[kind]=dict(n=len(selected),tasks=len({r['id'] for r in selected}),methods=methods,pairs=pairs,
                       reads=reads,repos=repos)
    costs=[json.loads(x) for x in (HERE/'measured'/'cost.jsonl').read_text().splitlines()]
    out['cost']={'tasks_processed':len(costs),'groups':sum(r['observed_groups'] for r in costs),
                 'pages':sum(r['pages'] for r in costs),'total_bytes':sum(r['bytes_on_disk'] for r in costs),
                 'median_bytes':np.median([r['bytes_on_disk'] for r in costs]),'mean_bytes':np.mean([r['bytes_on_disk'] for r in costs])}
    (HERE/'results.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    for kind in ('edit','control'):
        print(kind,out[kind]['n'],{m:v['full'] for m,v in out[kind]['methods'].items()},out[kind]['pairs']['address-direct'])


if __name__=='__main__':
    main()

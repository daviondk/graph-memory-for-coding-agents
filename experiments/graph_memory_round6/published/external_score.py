from collections import Counter
from hashlib import sha256
from pathlib import Path
import gzip
import json
from score import HERE,decode_output,paired,read
from hybrid_score import CAP,wire,stats,decode


def score(panel):
    ext=panel=='claude'
    prefix='external/' if ext else ''
    qs=read(prefix+'queries.jsonl.gz')
    gold=dict(read(prefix+'answers.jsonl.gz'))
    graphs=dict(read(prefix+'graph.jsonl.gz'))
    if ext:
        combined=dict(read('external/measured/rendered.jsonl.gz'))
    else:
        standard=dict(read('measured/rendered.jsonl.gz'))
        multi=dict(read('multiple_measured/rendered.jsonl.gz'))
        hybrid=dict(read('hybrid_measured/rendered.jsonl.gz'))
        combined={k:{'standard':v,'multiple':multi[k],'hybrid':hybrid[k]} for k,v in standard.items()}
    assert set(combined)==set(gold)==set(graphs)=={q['key'] for q in qs}
    records=[]
    for q in qs:
        k=q['key']
        combo=combined[k]
        multi=combo['multiple']
        multiple=decode(q,multi)
        multi_cost=stats(multi)
        graph=graphs[k]['address']
        lru=graphs[k]['lru_address']
        answers={'graph':graph,'lru':lru,'multiple':multiple}
        for mode,v in combo['standard'].items():
            answers[mode]=decode_output(v['rendered'],q['path'],q['lo'],q['n'])
        cost={'multiple':multi_cost}
        routes={}
        for name,hot_values in [('hybrid',graph),('lru_hybrid',lru)]:
            hot_bytes=wire(q,hot_values)
            hot=all(s is not None for s in hot_values) and len(hot_bytes)<=CAP
            routes[name]='hot' if hot else 'cold'
            answers[name]=hot_values if hot else multiple
            cost[name]=dict(calls=0,pages=0,bytes=len(hot_bytes)) if hot else multi_cost
            assert cost[name]['bytes']<=CAP
        actual=combo['hybrid']
        assert routes['hybrid']==actual['route']
        if actual['route']=='hot':
            assert json.loads(actual['response'])['lines']==answers['hybrid']
            assert len(actual['response'].encode())==cost['hybrid']['bytes']
        else:
            assert decode(q,actual['response'])==answers['hybrid']
            assert stats(actual['response'])==cost['hybrid']
        ans=gold[k]
        metrics={}
        for name,vals in answers.items():
            matches=sum(a==b for a,b in zip(vals,ans,strict=True))
            metrics[name]={'full':int(matches==len(ans)),'correct':matches,'returned':sum(a is not None for a in vals),
                           'wrong':sum(a is not None and a!=b for a,b in zip(vals,ans,strict=True)),
                           'compact_bytes':len(wire(q,vals))}
        records.append(dict(id=q['id'],repo=q['repo'],key=k,kind=q['kind'],n=q['n'],m=metrics,cost=cost,routes=routes))
    return records


def summary(data):
    methods=list(data[0]['m'])
    selected={m:{key:sum(r['m'][m][key] for r in data) for key in ('full','wrong','returned','correct','compact_bytes')}
              for m in methods}
    cpu={m:{key:sum(r['cost'][m][key] for r in data) for key in ('calls','pages','bytes')}
         for m in data[0]['cost']}
    contrasts=[('hybrid','multiple'),('hybrid','graph'),('hybrid','lru_hybrid'),('lru_hybrid','multiple'),
               ('lru_hybrid','lru'),('graph','multiple')]
    repos=sorted({r['repo'] for r in data})
    per={p:{m:sum(r['m'][m]['full'] for r in data if r['repo']==p) for m in methods}
         | {'n':sum(r['repo']==p for r in data)} for p in repos}
    n=len(data)
    leave={p:(selected['hybrid']['full']-selected['multiple']['full']-per[p]['hybrid']+per[p]['multiple'])/(n-per[p]['n'])
           for p in repos if n>per[p]['n']}
    return dict(n=n,tasks=len({r['id'] for r in data}),lines=sum(r['n'] for r in data),metrics=selected,cost=cpu,
                by_repo=per,leave_one_repo_out=leave,routes={m:dict(Counter(r['routes'][m] for r in data))
                for m in ('hybrid','lru_hybrid')},pairs={a+'-'+b:paired(data,a,b) for a,b in contrasts},
                repo_clusters_hybrid_minus_multiple=paired([{**r,'id':r['repo']} for r in data],'hybrid','multiple'))


if __name__=='__main__':
    seal=json.loads((HERE/'external_predictions.json').read_text())
    assert all(sha256((HERE/k).read_bytes()).hexdigest()==v for k,v in seal['files'].items())
    all_summary={}
    with gzip.open(HERE/'all_paired.jsonl.gz','wt',encoding='utf8') as dst:
        for panel in ('kimi','claude'):
            records=score(panel)
            all_summary[panel]={kind:summary([r for r in records if r['kind']==kind]) for kind in ('edit','control')}
            for r in records:
                dst.write(json.dumps(dict(panel=panel,**r),separators=(',',':'))+'\n')
            result=all_summary[panel]['edit']
            print(panel,{m:v['full'] for m,v in result['metrics'].items()},'cost',result['cost'],'pair',result['pairs']['hybrid-multiple'])
    (HERE/'all_results.json').write_text(json.dumps(all_summary,indent=2),encoding='utf8')

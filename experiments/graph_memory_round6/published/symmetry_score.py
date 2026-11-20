from collections import Counter
from hashlib import sha256
import gzip
import json
from score import HERE,read,paired
from hybrid_score import decode,stats,wire,CAP


def main():
    lock=json.loads((HERE/'symmetry_predictions.json').read_text())
    assert all(sha256((HERE/k).read_bytes()).hexdigest()==v for k,v in lock['files'].items())
    results=dict(read('external/symmetric/rendered.jsonl.gz'))
    oracle=dict(read('external/symmetric_oracle.jsonl.gz'))
    gold=dict(read('external/answers.jsonl.gz'))
    graph=dict(read('external/graph.jsonl.gz'))
    previous={r['key']:r for r in read('all_paired.jsonl.gz') if r['panel']=='claude'}
    data=[]
    for q in read('external/queries.jsonl.gz'):
        k=q['key']
        published=results[k]
        plain=decode(q,published['multiple'])
        rr=published['hybrid']
        if rr['route']=='hot':
            chosen=json.loads(rr['response'])['lines']
            assert chosen==graph[k]['address']
            cost={'calls':0,'pages':0,'bytes':len(rr['response'].encode())}
        else:
            chosen=decode(q,rr['response'])
            assert chosen==plain
            cost=stats(rr['response'])
            assert cost==stats(published['multiple'])
        lru=graph[k]['lru_address']
        use_lru=all(s is not None for s in lru) and len(wire(q,lru))<=CAP
        lru_cost= {'calls':0,'pages':0,'bytes':len(wire(q,lru))} if use_lru else stats(published['multiple'])
        assert all(c['bytes']<=CAP for c in [cost,lru_cost,stats(published['multiple'])])
        methods={**previous[k]['m']}
        for name,vals in [('sym_archive',plain),('sym_hybrid',chosen),('sym_lru_hybrid',lru if use_lru else plain),('uncapped_map',oracle[k])]:
            matches=sum(x==s for x,s in zip(vals,gold[k],strict=True))
            methods[name]={'full':int(matches==q['n']),'wrong':sum(x is not None and x!=s for x,s in zip(vals,gold[k],strict=True)),
                           'returned':sum(x is not None for x in vals),'correct':matches,'compact_bytes':len(wire(q,vals))}
        data.append(dict(id=q['id'],key=k,repo=q['repo'],kind=q['kind'],m=methods,
                         cost={'sym_archive':stats(published['multiple']),'sym_hybrid':cost,'sym_lru_hybrid':lru_cost}))
    with gzip.open(HERE/'symmetric_paired.jsonl.gz','wt',encoding='utf8') as f:
        for row in data:f.write(json.dumps(row,separators=(',',':'))+'\n')
    contrasts=[('sym_archive','multiple'),('sym_hybrid','sym_archive'),('sym_hybrid','hybrid'),('sym_hybrid','sym_lru_hybrid'),
               ('sym_archive','uncapped_map'),('sym_hybrid','graph')]
    out={}
    for kind in ('edit','control'):
        sample=[r for r in data if r['kind']==kind]
        methods={m:{key:sum(r['m'][m][key] for r in sample) for key in ('full','wrong','correct','returned','compact_bytes')}
                 for m in sample[0]['m']}
        out[kind]=dict(n=len(sample),metrics=methods,pairs={a+'-'+b:paired(sample,a,b) for a,b in contrasts},
                       cost={m:{key:sum(r['cost'][m][key] for r in sample) for key in ('bytes','calls','pages')}
                             for m in sample[0]['cost']})
    cost=[json.loads(l) for l in (HERE/'external/symmetric/cost.jsonl').read_text().splitlines()]
    base=[json.loads(l) for l in (HERE/'external/measured/cost.jsonl').read_text().splitlines()]
    out['write']={'symmetric':{k:sum(r[k] for r in cost) for k in cost[0] if k!='id'},
                  'original':{k:sum(r[k] for r in base) for k in ('observed_groups','pages','bytes_on_disk')}}
    (HERE/'symmetric_results.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    for kind in ('edit','control'):
        print(kind,{m:v['full'] for m,v in out[kind]['metrics'].items()},out[kind]['cost'])


if __name__=='__main__':
    main()

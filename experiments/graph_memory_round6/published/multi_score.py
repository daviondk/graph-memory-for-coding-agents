from collections import Counter
from hashlib import sha256
import gzip
import json
import numpy as np
from score import HERE,decode_output,paired,read


def main():
    lock=json.loads((HERE/'multi_predictions.json').read_text())
    assert all(sha256((HERE/k).read_bytes()).hexdigest()==v for k,v in lock['files'].items())
    q=read('paired.jsonl.gz')
    ans=dict(read('answers.jsonl.gz'))
    output=dict(read('multiple_measured/rendered.jsonl.gz'))
    assert len(q)==len(output)==278
    delta=[]
    for row in q:
        key=row['key']
        record=output[key]
        blocks={r['step']:decode_output(r['rendered'],row['path'],row['lo'],row['n']) for r in record['reads']}
        vals=[]
        for i in range(row['n']):
            step=record['owners'].get(str(row['lo']+i))
            if step is not None:
                assert step<=row['t']
            vals.append(blocks[step][i] if step in blocks else None)
        gold=ans[key]
        matched=[x==y for x,y in zip(vals,gold,strict=True)]
        metrics=dict(full=int(all(matched)),line_fraction=sum(matched)/len(gold),
                     wrong=sum(x is not None and x!=y for x,y in zip(vals,gold,strict=True)),
                     available=sum(x is not None for x in vals))
        delta.append(dict(id=row['id'],repo=row['repo'],key=key,kind=row['kind'],t=row['t'],
                          path=row['path'],lo=row['lo'],n=row['n'],predictions=vals,
                          calls=len(record['reads']),pages=sum(r['opened'] for r in record['reads']),
                          tokens=record['spent_tokens'],m={**row['m'],'multiple':metrics}))
    with gzip.open(HERE/'multi_paired.jsonl.gz','wt',encoding='utf8') as f:
        for row in delta:
            f.write(json.dumps(row)+'\n')
    summary={}
    for kind in ('edit','control'):
        data=[r for r in delta if r['kind']==kind]
        summary[kind]=dict(n=len(data),hits=sum(r['m']['multiple']['full'] for r in data),
                           mean_lines=np.mean([r['m']['multiple']['line_fraction'] for r in data]),
                           wrong=sum(r['m']['multiple']['wrong'] for r in data),
                           available=sum(r['m']['multiple']['available'] for r in data),
                           calls=sum(r['calls'] for r in data),pages=sum(r['pages'] for r in data),
                           call_histogram=dict(Counter(r['calls'] for r in data)),
                           mean_tokens=np.mean([r['tokens'] for r in data]),
                           max_tokens=max(r['tokens'] for r in data),
                           vs_graph=paired(data,'address','multiple'),vs_single=paired(data,'multiple','direct'),
                           vs_lru=paired(data,'lru_address','multiple'),
                           repo_hits={p:sum(r['m']['multiple']['full'] for r in data if r['repo']==p)
                                     for p in sorted({r['repo'] for r in data})})
    (HERE/'multi_results.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary))


if __name__=='__main__':
    main()

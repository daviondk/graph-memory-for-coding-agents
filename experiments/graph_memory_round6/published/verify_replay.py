"""Read-only verification of sealed inputs/results and replayed public answer frames."""
import argparse
import hashlib
import json
from score import HERE,read,decode_output
from hybrid_score import decode,stats

MODES={'kimi':'measured','kimi_multi':'multiple_measured','kimi_hybrid':'hybrid_measured',
       'claude':'external/measured','aligned':'external/symmetric'}


def normalize(kind,row,q):
    if kind=='standard':
        return {m:(v['status'],v['pages_read'],decode_output(v['rendered'],q['path'],q['lo'],q['n'])) for m,v in row.items()}
    if kind=='multi':
        return [decode(q,row),stats(row)]
    if kind=='hybrid':
        if row['route']=='hot':
            return ['hot',json.loads(row['response'])]
        return ['cold',normalize('multi',row['response'],q)]
    if kind=='aligned':
        return [normalize('multi',row['multiple'],q),normalize('hybrid',row['hybrid'],q)]
    return [normalize('standard',row['standard'],q),normalize('multi',row['multiple'],q),normalize('hybrid',row['hybrid'],q)]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',choices=MODES)
    ap.add_argument('--actual')
    op=ap.parse_args()
    for filename in ('design_freeze.json','method_freeze.json','prediction_freeze.json','multi_freeze.json',
                     'multi_predictions.json','hybrid_freeze.json','hybrid_predictions.json','lru_design.json',
                     'external_design.json','external_methods.json','external_predictions.json','symmetry_design.json',
                     'symmetry_method.json','symmetry_predictions.json'):
        sealed=json.loads((HERE/filename).read_text())
        for p,dg in sealed['files'].items():
            assert hashlib.sha256((HERE/p).read_bytes()).hexdigest()==dg,(filename,p)
    if op.mode:
        name=MODES[op.mode]
        prefix='external/' if op.mode in ('claude','aligned') else ''
        queries={q['key']:q for q in read(prefix+'queries.jsonl.gz')}
        baseline=dict(read(name+'/rendered.jsonl.gz'))
        actual=dict(read((op.actual or name)+'/rendered.jsonl.gz'))
        kind={'kimi':'standard','kimi_multi':'multi','kimi_hybrid':'hybrid','claude':'all','aligned':'aligned'}[op.mode]
        assert actual.keys()==baseline.keys()==queries.keys()
        for k,q in queries.items():
            assert normalize(kind,actual[k],q)==normalize(kind,baseline[k],q),(op.mode,k)
        print(op.mode,len(actual),'per-query public readouts and costs verified')
    else:
        oracle=dict(read('external/symmetric_oracle.jsonl.gz'))
        native=dict(read('external/symmetric/rendered.jsonl.gz'))
        for q in read('external/queries.jsonl.gz'):
            k=q['key']
            a,b=native[k]['multiple'],native[k]['hybrid']
            x=decode(q,a)
            y=json.loads(b['response'])['lines'] if b['route']=='hot' else decode(q,b['response'])
            assert x==y==oracle[k],k
        print('All 14 freeze files and 232 exact equality checks verified.')


if __name__=='__main__':
    main()

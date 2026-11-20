from hashlib import sha256
from collections import Counter
import gzip
import json
from score import HERE,decode_output,paired,read

CAP=98304


def wire(q,lines):
    return json.dumps({'file':q['path'],'first':q['lo'],'lines':lines},ensure_ascii=False,separators=(',',':')).encode()


def decode(q,record):
    blocks={r['step']:decode_output(r['rendered'],q['path'],q['lo'],q['n']) for r in record['reads']}
    result=[]
    for i in range(q['n']):
        owner=record['owners'].get(str(q['lo']+i))
        result.append(blocks[owner][i] if owner in blocks else None)
    return result


def stats(record):
    return {'calls':len(record['reads']),'pages':sum(r['opened'] for r in record['reads']),
            'bytes':sum(len(r['rendered'].encode()) for r in record['reads'])}


def main():
    seal=json.loads((HERE/'hybrid_predictions.json').read_text())
    assert all(sha256((HERE/k).read_bytes()).hexdigest()==v for k,v in seal['files'].items())
    conditional=dict(read('hybrid_measured/rendered.jsonl.gz'))
    native=dict(read('multiple_measured/rendered.jsonl.gz'))
    hot=dict(read('graph.jsonl.gz'))
    truth=dict(read('answers.jsonl.gz'))
    source={r['key']:r for r in read('multi_paired.jsonl.gz')}
    data=[]
    for q in read('queries.jsonl.gz'):
        k=q['key']
        graph=hot[k]['address']
        item=conditional[k]
        oracle=truth[k]
        cold=decode(q,native[k])
        assert cold==source[k]['predictions']
        charged=stats(native[k])
        if item['route']=='hot':
            assert all(x is not None for x in graph)
            output=json.loads(item['response'])
            assert output['file']==q['path'] and output['first']==q['lo']
            chosen=output['lines']
            assert chosen==graph
            hybrid_charge={'calls':0,'pages':0,'bytes':len(item['response'].encode())}
        else:
            assert any(x is None for x in graph) or len(wire(q,graph))>CAP
            chosen=decode(q,item['response'])
            assert chosen==cold
            hybrid_charge=stats(item['response'])
            assert hybrid_charge==charged
        assert hybrid_charge['bytes']<=CAP and charged['bytes']<=CAP
        ms={name:{'full':int(values==oracle),'wrong':sum(s is not None and s!=t for s,t in zip(values,oracle,strict=True))}
            for name,values in [('graph',graph),('multiple',cold),('hybrid',chosen)]}
        useful={name:len(wire(q,values)) for name,values in [('graph',graph),('multiple',cold),('hybrid',chosen)]}
        assert max(useful.values())<=CAP
        data.append(dict(key=k,id=q['id'],kind=q['kind'],route=item['route'],m=ms,multiple_cost=charged,
                         hybrid_cost=hybrid_charge,useful_response_bytes=useful))
    with gzip.open(HERE/'hybrid_paired.jsonl.gz','wt',encoding='utf8') as f:
        for row in data:
            f.write(json.dumps(row)+'\n')
    out={}
    for kind in ('edit','control'):
        cohort=[r for r in data if r['kind']==kind]
        out[kind]={'n':len(cohort),'routes':dict(Counter(r['route'] for r in cohort)),
                   'hits':{m:sum(r['m'][m]['full'] for r in cohort) for m in ('graph','multiple','hybrid')},
                   'wrong':{m:sum(r['m'][m]['wrong'] for r in cohort) for m in ('graph','multiple','hybrid')},
                   'route_hits':{s:sum(r['m']['hybrid']['full'] for r in cohort if r['route']==s) for s in ('cold','hot')},
                   'cost':{m:{p:sum(r[m+'_cost'][p] for r in cohort) for p in ('calls','pages','bytes')} for m in ('multiple','hybrid')},
                   'useful_bytes':{m:sum(r['useful_response_bytes'][m] for r in cohort) for m in ('graph','multiple','hybrid')},
                   'vs_graph':paired(cohort,'hybrid','graph'),'vs_multiple':paired(cohort,'hybrid','multiple')}
    (HERE/'hybrid_results.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print(json.dumps(out))


if __name__=='__main__':
    main()

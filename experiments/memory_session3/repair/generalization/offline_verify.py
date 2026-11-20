"""Offline audit using only files in this directory and CPython's standard library."""
import collections,csv,hashlib,json
from pathlib import Path
from oracle import valid
R=Path(__file__).resolve().parent
def read(n):return json.loads((R/n).read_text(encoding='utf8'))
def sha(x):return hashlib.sha256(x).hexdigest()
def key(x):return sha(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
def main():
    for f,h in read('lock.json')['sha256'].items():assert sha((R/f).read_bytes())==h
    independent=read('public_input_hashes.json')
    assignments=read('assignments.json');cases=read('cases.json')
    with (R/'per_program.csv').open(encoding='utf8') as f:table={r['program']:r for r in csv.DictReader(f)}
    result=read('results.json'); arms=['reference','original','empty','recent','witness','full']
    unique=set();solved=collections.Counter();counts=collections.Counter()
    assert set(table)==set(cases)==set(assignments)
    for name,inputs in cases.items():
        assert len(inputs)==len({key(c['input']) for c in inputs})==16
        assert all(key(c['input'])==c['key'] and c['key'] not in independent[name] for c in inputs)
        for arm in arms:
            h=assignments[name][arm];unique.add((name,h))
            receipt=read('receipts/'+name+'-'+h+'.json');ok=0
            assert len(receipt)==len(inputs)
            for record,c in zip(receipt,inputs):
                assert record['key']==c['key']
                obs=record['observation']
                actual=obs['status']=='return' and valid(name,c['input'],obs['value'])
                assert actual==record['ok']
                ok+=actual
            assert int(table[name][arm])==ok
            counts[arm]+=ok;solved[arm]+=ok==len(inputs)
    assert dict(counts)==result['primary']['passed_inputs'] and dict(solved)==result['primary']['success']
    assert len(unique)==result['distinct_all_programs']
    print('Standalone verified:',len(unique),'modules;',sum(map(len,cases.values())),'distinct new inputs;',dict(solved))
if __name__=='__main__':main()

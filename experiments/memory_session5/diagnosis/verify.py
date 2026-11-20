"""Replay original decisions and independently inspect all transfer packet bounds and outcomes."""
import collections,gzip,itertools,json,hashlib,sys
from pathlib import Path
from predict import read,rows,ROOT
from score import summarize,score
def doc(path):return json.loads(path.read_bytes())
def verify_hashes(path,mapping):
    for name,digest in mapping.items():
        assert hashlib.sha256((path/name).read_bytes()).hexdigest()==digest,name
def main():
    transfer=ROOT/'transfer'
    sys.path.insert(0,str(transfer))
    from run import collect,histories
    from diagnose import diagnostics
    verify_hashes(ROOT,doc(ROOT/'decision_lock.json'))
    verify_hashes(ROOT,doc(ROOT/'input_lock.json')['files'])
    verify_hashes(transfer,doc(transfer/'lock.json'))
    verify_hashes(ROOT/'raw',{n:v['sha256'] for n,v in doc(ROOT/'source.json').items()})
    corpus=read('cycles.json.gz')
    with gzip.open(ROOT/'rankings.jsonl.gz','rt') as f:
        n=0
        for reconstructed,stored in itertools.zip_longest(rows(corpus),f):
            assert json.loads(json.dumps(reconstructed))==json.loads(stored)
            n+=1
    assert summarize(score())==doc(ROOT/'results.json')
    sessions=collect();states=list(histories(sessions))
    stored=[json.loads(l) for l in gzip.decompress((transfer/'outputs.jsonl.gz').read_bytes()).splitlines()]
    assert len(states)==len(stored)
    bytesums=collections.defaultdict(list)
    for r,logged in zip(states,stored):
        actual=logged['methods'];base=r['methods']
        for k,v in base.items():assert actual[k]==v
        assert set(base['fixed']['chosen'])==set(base['minimal']['chosen'])
        def size(m):return len(bytes.fromhex(actual[m]['packet']))
        bytesums[logged['setting'],logged['system']].append([size(k) for k in ['minimal','matched_recent','matched_surprise']])
    for vs in bytesums.values():assert len(set(map(sum,zip(*vs))))==1
    assert json.loads(json.dumps(diagnostics()))==doc(transfer/'analysis.json')
    print(f'PASS {n} original and {len(stored)} transfer decisions; current-outcome metrics, calibration, packet costs and locked checksums')
if __name__=='__main__':main()

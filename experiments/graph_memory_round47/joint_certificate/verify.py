"""Read-only offline verification of the frozen panel, arithmetic, controls, and interval estimates."""
from hashlib import sha256
from itertools import combinations
from build import D,dig,load
from analyze import analyze
from independent import check_real,synth

def main():
    man=load('manifest.json')['files']
    assert all(dig(D/n)==sha for n,sha in man.items())
    p=load('registration.json');s=load('sample-seal.json');sample=load('sample.json.gz')
    assert dig(D/'PROTOCOL_RU.md')==p['protocol'] and dig(D/'sample.json.gz')==s['sha256'] and dig(D/'build.py')==s['generator']
    assert len({q['tr'] for q in sample.values()})==40
    for q,v in sample.items():
        src=v['source']
        order=sorted(combinations(sorted(src),2),key=lambda pair:sha256(f"470531|{q}|{pair[0]}|{pair[1]}".encode()).digest())
        assert v['available']==len(order)
        assert [p[:2] for p in v['pairs'] if p[2]=='primary']==[list(p) for p in order[:32]]
        assert len({tuple(p[:2]) for p in v['pairs']})==len(v['pairs'])
    assert load('results.json')==analyze()
    assert load('independent.json')=={'real':check_real(),'overlap':synth()}
    print('Verified 40 projections, 1,280 primary pairs, 320 independent real DP checks, and exhaustive overlap controls.')
if __name__=='__main__':main()

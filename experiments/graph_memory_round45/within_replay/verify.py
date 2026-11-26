"""Portable verification of frozen ranks, scoring receipts, shared-epoch identities and bootstrap."""
import hashlib,json
from pathlib import Path
from analyze import D,read,run
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    m=read(D/'manifest.json')['files']
    assert all(sha(D/k)==v for k,v in m.items())
    reg=read(D/'registration.json');older=read(D/'registration-v1.json')
    assert reg['protocol']==sha(D/'PROTOCOL_RU.md') and reg['code']==sha(D/'forecast.py')
    assert all(reg[k]==older[k] for k in ('protocol','pairs','r43','split'))
    assert sum(c['recall']!=c['budget'] for c in reg['pairs'].values())==5
    models={f'{tag.split("-",1)[0]}/{tag.split("-",1)[1]}/{e}' for tag,choice in reg['pairs'].items() for e in choice['states']}
    assert len(models)==15
    seen={};seal=read(D/'forecast-seal.json');assert seal['registration']==sha(D/'registration.json')
    for part in seal['shards']:
        p=D/part['file'];assert sha(p)==part['sha']
        rows=read(p);assert not seen.keys()&rows.keys()
        for q,(t,preds) in rows.items():
            assert preds.keys()==models
            n=len(next(iter(preds.values())));assert n>0 and all(sorted(order)==list(range(n)) for order in preds.values())
            seen[q]=t
    assert len(seen)==2000 and len(set(seen.values()))==1207
    scores=read(D/'scores.json.gz');assert {q:v[0] for q,v in scores.items()}==seen
    assert read(D/'results.json')==run()
    print('Verified 30000 paired CPU rankings, 2000 questions, 5 seeds, gold-score seals and within-run contrasts.')
if __name__=='__main__':main()


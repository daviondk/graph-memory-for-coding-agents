import gzip,hashlib,json,sys
from pathlib import Path
D=Path(__file__).resolve().parent
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def r(p):
    p=D/p;return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def main():
    fit=r('fit-lock.json'); assert fit['q']==500 and fit['weights']==h(D/'weights.json')
    seal=r('forecast-seal.json');assert seal['fit']==h(D/'fit-lock.json')
    preds={}
    for fp,d in seal['shards'].items():
        assert d==h(D/fp)
        for z in r(fp):
            assert z['q'] not in preds
            preds[z['q']]=z
    rows=r('test-outcomes.json.gz');assert len(rows)==len(preds)==2000
    for z in rows:
        p=preds[z['q']];assert z['t']==p['t'] and z['pilot']==p['pilot'] and set(z['arms'])==set(p['picks'])
        assert all(v['fs'] in (0,1) and 0<=v['tokens']<=2048 for v in z['arms'].values())
    p=r('test-results.json')['primary'];assert p['q']==1845 and p['t']==1111
    for k,t in p['means'].items():assert t['hits']==sum(z['arms'][k]['fs'] for z in rows if not z['pilot'])
    if (D/'extra-results.json').exists():
        assert r('forecast-extra-lock.json')['forecast']==h(D/'forecast-extra.json.gz')
        assert r('extra-results.json')['novel']['q']==len(r('extra-outcomes.json.gz'))==27
    out={p.name:h(p) for p in sorted(D.iterdir()) if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    if '--seal' in sys.argv:(D/'MANIFEST_SHA256.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n',encoding='utf8')
    assert out==r('MANIFEST_SHA256.json')
    print('verified',len(out),'files')
if __name__=='__main__':main()


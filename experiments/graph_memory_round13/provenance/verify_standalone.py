"""Verify the portable result tables without external repositories, packages or Git."""
import argparse,gzip,hashlib,json,math
from collections import Counter
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
def main():
    arg=argparse.ArgumentParser();arg.add_argument('--seal',action='store_true',help='write verification and a new local manifest');seal=arg.parse_args().seal
    if not seal:
        m=read(D/'MANIFEST_SHA256.json')
        for k,v in m.items():
            path=D/k;assert path.resolve().is_relative_to(D) and h(path)==v,k
    r=read(D/'results.json');pred=read(D/'features.json.gz');labs=read(D/'direct_receipts.json');raw=read(D/'graded.json.gz');lock=read(D/'forecast_lock.json')
    assert len(labs)==len(pred)==len(raw)==r['evaluable']==r['total']==147 and set(labs)=={q['id'] for q in pred}
    for k,v in lock['code'].items():assert h(D/k)==v
    assert h(D/'features.json.gz')==lock['features'] and h(D/'operations.json')==lock['operations']
    assert all(len(labs[a]['ns'])==3 for a in labs)
    by={q['id']:q for q in raw}
    truth={k:int(s['hit']) for k,s in labs.items()};assert sum(truth.values())==29
    for a,c in r['primary'].items():
        yes=[q['id'] for q in pred if q['trust'][a]]
        assert len(yes)==c['reused'] and sum(truth[i] for i in yes)==c['unsafe_reused'] and len(labs)-len(yes)==c['rescans']
        assert c['risk'] is None if not yes else close(c['risk'],sum(truth[i] for i in yes)/len(yes))
        assert all(q['trust'][a]==by[q['id']]['forecasts'][a] and truth[q['id']]==by[q['id']]['hit'] for q in pred)
    stable=lambda q:hashlib.sha256(q['id'].encode()).hexdigest()
    orders={'rank':sorted(pred,key=lambda q:(tuple(-v for v in q['score']),stable(q))),'hash':sorted(pred,key=stable)}
    for mode,ordered in orders.items():
        count=0;auc=0
        for i,q in enumerate(ordered,1):
            count+=truth[q['id']];auc+=count/i
            for k,cell in r['curves'][mode].items():
                if k!='aurc' and cell['reused']==i:assert cell['unsafe_reused']==count
        assert close(auc/len(ordered),r['curves'][mode]['aurc'])
    ext=read(D/'external'/'results.json');z=read(D/'external'/'graded.json.gz');good=[o for o in z if o['valid']]
    assert len(z)==31 and len(good)==ext['nvalid']==28 and sum(o['hit'] for o in good)==ext['n_unsafe']==0
    for a,c in ext['policies'].items():assert c['reused']==sum(o['trust'][a] for o in good)
    extlock=read(D/'external'/'lock.json');assert h(D/'external'/'forecasts.json.gz')==extlock['forecasts']
    twins=read(D/'controlled_results.json');nr=0
    for a,b in zip(twins['records'][::2],twins['records'][1::2],strict=True):
        assert a['trial']==b['trial'] and a['kind']==b['kind'] and (a['git_return'],b['git_return'])==(1,0)
        if a['kind']!='visible':assert a['features']==b['features'];nr+=1
        else:assert not a['features']['prior_positive'] and b['features']['prior_positive']
        for row in (a,b):
            code=hashlib.sha256(f"twin|{row['trial']}".encode()).hexdigest()[:12]
            for name,v in row['input_files'].items():assert h(D/'controlled'/code/row['kind']/row['condition']/name)==v
    assert nr==24
    output=dict(raw_primary=147,unsafe_primary=29,verified_primary_policies=len(r['primary']),graded_ranks_recomputed=True,external_n=31,external_valid=28,external_unsafe=0,twins=36,indistinguishable_pairs=24,temporal=read(D/'prefix_verification.json'),read_only_mode=not seal)
    if seal:
        output.pop('read_only_mode');(D/'verification.json').write_text(json.dumps(output,indent=1)+'\n',encoding='utf8')
        files=[p for p in D.rglob('*') if p.is_file() and p.suffix!='.pyc' and '__pycache__' not in p.parts and p.name!='MANIFEST_SHA256.json']
        manifest={p.relative_to(D).as_posix():h(p) for p in sorted(files)}
        (D/'MANIFEST_SHA256.json').write_text(json.dumps(manifest,indent=1,sort_keys=True)+'\n',encoding='utf8')
    print(json.dumps(output,ensure_ascii=True))
if __name__=='__main__':main()
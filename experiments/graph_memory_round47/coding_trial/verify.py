"""Pure standard-library verification of all official profiles, native parser labels, and independent JUnit records."""
import gzip,hashlib,importlib.util,json,sys
from collections import Counter
from pathlib import Path
from suite import parse
D=Path(__file__).resolve().parent
def read(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    man=read(D/'manifest.json')['files']
    for n,s in man.items():assert sha((D/n).read_bytes())==s,n
    q=read(D/'inputs/grade-case.json.gz');lock=read(D/'locked.json');imgs=read(D/'image.json')
    sys.path.insert(0,str(D/'inputs/vendor'))
    from log_parsers import parse_log_pytest
    primary=read(D/'grading/scores.json');assert primary['lock_sha256']==sha((D/'locked.json').read_bytes())
    gen=read(D/'suite/summary.json');profiles=read(D/'suite/profiles.json.gz')
    manifest_ids=['base','reference',*lock['cases']]
    assert set(gen)==set(profiles)==set(primary['outcomes'])==set(manifest_ids)
    ids=set(q['FAIL_TO_PASS']+q['PASS_TO_PASS']);assert len(ids)==16
    for case in manifest_ids:
        p=primary['outcomes'][case];log=(D/'grading'/(case+'.log')).read_bytes()
        assert p['log_sha256']==sha(log)
        observed=parse_log_pytest(log.decode('utf8'))
        passed={k for k,s in observed.items() if s=='PASSED'}
        assert all(k in observed for k in ids)
        assert p['official_exact']==(passed==ids)==(case!='base')
        assert p['test_patch_sha256']==sha(q['test_patch'].encode())
        patch=b'' if case=='base' else q['patch'].encode() if case=='reference' else (D/lock['cases'][case]['path']).read_bytes()
        assert sha(patch)==p['patch_sha256']
        for k,group in [('FAIL_TO_PASS','f2p'),('PASS_TO_PASS','p2p')]:
            assert p[group]==[len(passed&set(q[k])),len(q[k])]
        for key,expected in [('fail_to_pass',q['FAIL_TO_PASS']),('pass_to_pass',q['PASS_TO_PASS'])]:
            assert p['registered_statuses'][key]=={n:observed[n] for n in expected}
        record=gen[case]
        for ext in ('log','xml'):
            raw=gzip.decompress((D/'suite'/(case+'.'+ext+'.gz')).read_bytes())
            assert sha(raw)==record[ext+'_sha256']
        statuses=parse(raw)
        assert statuses==profiles[case] and len(statuses)==509 and dict(Counter(statuses.values()))==record['status']
        assert all(statuses[name]==observed[name] for name in ids)
        assert all(statuses[name]==profiles['base'][name] for name in statuses.keys()-ids)
    assert imgs['image_provenance']['content_sha256']==imgs['source']['source_content_sha256']
    print('Verified 5 official profiles, 80 registered statuses and 2,545 suite test IDs with preserved teardown outcomes.')
if __name__=='__main__':main()

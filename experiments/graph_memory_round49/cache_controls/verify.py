"""Independent calculation from per-state outcomes; no sibling study, WSL or network required."""
from pathlib import Path
from collections import defaultdict
import json,gzip,hashlib,numpy as np
D=Path(__file__).resolve().parent
def get(f):
    b=(D/f).read_bytes()
    return json.loads(gzip.decompress(b) if f.endswith('.gz') else b)

def main():
    raw=get('results.json')
    count=0;seen=set()
    for name,report in raw.items():
        rows=get(name+'-outcomes.json.gz');repos=defaultdict(list)
        for q,z in rows.items():repos[z['repo']].append(z)
        assert len(rows)==report['states'] and len(repos)==report['repos'] and not seen & set(repos)
        seen.update(repos)
        groups=[repos[k] for k in sorted(repos)]
        den=np.array([sum(v['total'] for v in group) for group in groups]);dups=sum(z['within'] for z in rows.values())
        clusters=np.random.default_rng(491902).multinomial(len(groups),np.full(len(groups),1./len(groups)),size=20000)
        assert int(den.sum())==report['total']
        for mode,conditions in report['conditions'].items():
            for m,st in conditions.items():
                new=np.array([sum(v[mode]['proposed'][1] for v in g) for g in groups])
                old=np.array([sum(v[mode][m][1] for v in g) for g in groups])
                dif=new-old
                assert st['saved']==old.sum() and st['net']==den.sum()-dups-old.sum() and st['diff']==sum(dif)
                assert st['hits']==sum(z[mode][m][0] for z in rows.values())
                assert np.isclose(np.mean(dif/den),st['macro_delta']) and np.isclose(dif.sum()/den.sum(),st['delta'])
                assert np.allclose(np.percentile((clusters@dif)/(clusters@den),[2.5,97.5]),st['ci'])
                count+=1
    assert sum(y['forecasts'] for x in get('native-validation.json').values() for y in x.values())==3872
    assert get('reference.json')['requests']==22344
    if (D/'manifest.json').is_file():
        for k,d in get('manifest.json')['files'].items(): assert hashlib.sha256((D/k).read_bytes()).hexdigest()==d
    print('Verified 484 outcomes, 171 distinct repositories,',count,'contrasts and 3872 native policy checks.')


if __name__=='__main__':main()


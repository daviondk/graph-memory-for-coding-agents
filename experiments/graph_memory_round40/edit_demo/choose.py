"""Choose predeclared demonstration cases from frozen outcomes, without reading source text."""
from hashlib import sha256
from pathlib import Path
import gzip
import json

D=Path(__file__).resolve().parent
R40=D.parent
WORK=R40.parent

def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def choose():
    span=R40/'span_updates';nat=R40/'natural_invalidations';audit=read(span/'audit_strict.json')
    assert digest(span/'scored.json.gz')==audit['sealed']==read(span/'results.json')['forecasts']
    assert digest(span/'audit_strict_rows.json.gz')==audit['checks']
    assert digest(nat/'plans.json.gz')==read(nat/'manifest.json')['files']['plans.json.gz']
    verified=read(span/'manifest.json')
    for filename in ('scored.json.gz','audit_strict_rows.json.gz','audit_strict.json','results.json'):
        assert digest(span/filename)==verified.get('files',verified)[filename]
    scored=read(span/'scored.json.gz');counts={(r,a):c for r,a,c in read(span/'audit_strict_rows.json.gz')}
    plans=read(nat/'plans.json.gz')
    picked={};used=set()
    for role in ('relocated','changed','stale'):
        for s in sorted(scored,key=lambda row:(row['rid'],row['event'])):
            r,at=s['rid'],s['event'];b=plans[r][str(at)];cnt=counts[r,s['receipt']]
            if r in used or s['group']!='main' or len(set(c[0] for c in b))!=1 or not 2<=len(b)<=(100 if role=='stale' else 30) or not s['old'] or not s['new'] or not s['eligible'] or s['file_reuse']:continue
            good=not cnt.get('post_mismatch',0) and not cnt.get('prior_mismatch',0)
            if role=='relocated':fits=good and s['range_reuse'] and not s['same_coords']
            elif role=='changed':fits=good and not s['range_reuse']
            else:fits=s['range_reuse'] and cnt.get('reused_selected_post_mismatch',0)>0 and not cnt.get('new_mismatch',0)
            if fits:
                picked[role]=(s,b,cnt);used.add(r);break
    assert list(picked)==['relocated','changed','stale'],list(picked)
    return picked
if __name__=='__main__':
    for c,(s,b,n) in choose().items():print(c,s['event'],len(b),s['old'],s['new'],s['delta'],n)

"""Verify literal editing against downloaded full source files without modifying artifacts."""
import gzip,hashlib,json
from pathlib import Path
from collections import Counter
R=Path(__file__).resolve().parent;P=R/'native'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    src=read(P/'sources.json');select=read(P/'sample.json'); rows=read(P/'physical_rows.json');result=read(P/'results.json')
    assert len(src)==len(select)==240
    assert [{k:r[k] for k in select[0]} for r in src]==select
    for r in src:
        if r['status']==200:
            x=gzip.decompress((P/'blobs'/(r['blob_sha256']+'.gz')).read_bytes())
            assert hashlib.sha256(x).hexdigest()==r['blob_sha256'] and len(r['commit'])==40
    for r in rows:
        if r['full_unique']:
            fn=hashlib.sha256((r['traj']+'|'+str(r['tool_time'])).encode()).hexdigest()+'.txt'
            assert sha(P/'executed'/fn)==r['executed_sha256']
    good={(r['shard'],r['row'],r['cut']) for r in rows if r['full_unique'] and r['post_snippet_agrees'] and r['historically_accepted']}
    keys={(r['shard'],r['row'],r['cut']) for r in rows}
    assert result['confirmed_physical_replacements']==len(good)
    assert result['full_unique']==sum(r['full_unique'] for r in rows)
    counts={}
    for fn in sorted((R/'scores').glob('*.gz')):
        with gzip.open(fn,'rt',encoding='utf8') as f:
            for ln in f:
                q=json.loads(ln);key=q['shard'],q['row'],q['cut']
                if key not in keys:continue
                for arm,(ph,hit,tok) in q['metrics'].items():
                    d=counts.setdefault(arm,Counter());d['opportunities']+=1;d['native_validated_opportunities']+=key in good;d['recovered_and_native_confirmed']+=bool(hit and key in good);d['historical_excerpt_recovered']+=hit
    assert dict(counts)==result['policies']
    print('Verified 240 independently sampled full-file sources,',len(rows),'historical replacements,',len(good),'source-confirmed edits.')
if __name__=='__main__':main()

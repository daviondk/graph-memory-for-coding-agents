"""Portable independent audit of the sealed panels, I/O accounts, range facts and fixtures."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path
from locator import selftest

D=Path(__file__).resolve().parent
def read(n):
    raw=(D/n).read_bytes();return json.loads(gzip.decompress(raw) if n.endswith('.gz') else raw)
def digest(n):return sha256((D/n).read_bytes()).hexdigest()

def verify():
    if (D/'manifest.json').is_file():
        for n,v in read('manifest.json')['files'].items():assert digest(n)==v,n
    seal=read('panel-seal.json');method=read('method-seal.json');score=read('score-seal.json');lit=read('literal-audit.json')
    assert digest('PROTOCOL_RU.md')==seal['protocol']==method['protocol']
    assert digest('source.py')==seal['source_code'] and digest('panel.json.gz')==seal['files']['panel'] and digest('tails.json.gz')==seal['files']['tails']
    assert (digest('panel-seal.json'),digest('locator.py'),digest('evaluate.py'))==(method['panel'],method['locator'],method['evaluator'])
    assert digest('method-seal.json')==score['method'] and digest('outcomes.json.gz')==score['outcomes']==lit['native']
    assert selftest()==score['fixtures']
    panel=read('panel.json.gz');out={int(i):o for i,o in read('outcomes.json.gz').items()};tails=read('tails.json.gz')
    assert len(panel)==21783 and sum(r[11] for r in panel)==19655 and all(len(r)==15 for r in panel)
    assert len(set((r[0],r[1]) for r in panel))==len(panel)
    assert Counter(r[12] for r in panel)=={'known':2696,'novel':1421,'extra':17666}
    assert set(out)=={i for i,r in enumerate(panel) if r[8]=='tail' and r[2] is not None}
    for key,t in tails.items():assert sha256(json.dumps(t,separators=(',',':')).encode()).hexdigest()==key
    accepted=0;all_lines=0;accepted_lines=0
    for i,o in out.items():
        r=panel[i];token=tails[r[9]];counts=len(token);maximum=sum(t[0] for t in token)+2*counts+4;all_lines+=counts
        assert o['full_calls']==1 and o['tail_lines']==counts
        expected=min(o['full_read'],maximum) if r[6]=='eof' else 0
        assert o['bytes_read']==expected and o['read_calls']==(expected+4095)//4096
        if o['span']:
            assert o['status']=='verified_at_receipt' and r[6]=='eof' and o['placements']==1
            assert o['span']==o['unique_placement'][:3] and o['unique_placement'][4]-o['unique_placement'][3]+1==counts
            assert 0<=o['span'][0]<=o['span'][1]<=o['full_read'] and len(bytes.fromhex(o['span'][2]))==32
            accepted+=1;accepted_lines+=counts
        else:assert o['status'] in ('unsupported_request','suffix_mismatch')
    assert (accepted,accepted_lines,len(out),all_lines)==(679,162036,705,167805)
    assert lit['counts']=={'accepted_byte_ranges':accepted,'accepted_rendered_lines':accepted_lines,'literal_scans':len(out),'rendered_lines':all_lines}
    groups=read('results.json')['groups']
    for name,rows in [('known',[i for i,r in enumerate(panel) if r[12]=='known']),('novel',[i for i,r in enumerate(panel) if r[12]=='novel']),('all_parsed_views',range(len(panel)))]:
        sub=[out[i] for i in rows if i in out];g=groups[name]
        assert len(rows)==g['views'] and len(sub)==g['scored'] and sum(bool(o['span']) for o in sub)==g['accepted']
        assert sum(o['bytes_read'] for o in sub)==g['read_bytes'] and sum(o['full_read'] for o in sub if o['read_calls'])==g['full_bytes_on_same_attempts']
    print('Verified 21,783 source views, 705 paired full scans, 679 byte witnesses, three summary panels and eleven edge cases.')
if __name__=='__main__':verify()

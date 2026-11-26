"""Verify stored data, recompute all 160 packets and interval coverages offline."""
import gzip
import hashlib
import json
from pathlib import Path
from reader import D,Reader,Evaluator,choose_tail

def require(ok,message):
    if not ok:raise ValueError(message)

def content(path):
    raw=path.read_bytes();return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def verify():
    manifest=content(D/'manifest.json')['files']; digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,expected in manifest.items():
        path=(D/name).resolve();require(path.is_relative_to(D) and digest(path)==expected,name)
    r=Reader();g=Evaluator();ref=content(D/'reference.json');obs=content(D/'observations.json.gz');panel=content(D/'panel.json');provenance=content(D/'provenance.json');report=content(D/'results.json')
    require(digest(D/'PROTOCOL_RU.md')==panel['protocol'] and len({i['trajectory'] for i in panel['queries']})==40,'selection')
    require(r.db.execute('PRAGMA integrity_check').fetchone()==('ok',) and g.db.execute('PRAGMA integrity_check').fetchone()==('ok',),'database integrity')
    require({x[0] for x in r.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}=={'query','node','origin','span','edge'},'metadata schema')
    for name,expected in provenance['databases'].items():require(digest(D/name)==expected,name)
    require(list(r.queries())==sorted(obs)==sorted(ref) and len(ref)==40,'query panel')
    ties=choose_tail([(1,0,1,1.0),(2,1,1,1.0),(3,2,0,0.5)],1);require([x[0] for x in ties]==[1,3],'DP tie-breaking')
    for q,arms in obs.items():
        truth=ref[q];base=arms['main'];require(base['ids']==truth['ids'] and [base['full_support'],base['tokens'],len(base['ids'])]==[truth['official'][0],truth['official'][2],truth['official'][3]] and abs(base['coverage']-truth['official'][1])<1e-12,'frozen comparison '+q)
        for key,value in arms.items():
            result=r.choose(q,value['budget'],value['exclude']);ev=g.evaluate(r,result)
            require(all(value[k]==v for k,v in {**result,**ev}.items()) and len(value['elapsed_ns'])==5 and all(t>0 for t in value['elapsed_ns']),f'{q}/{key}')
    for key,summary in report['arms'].items():
        require(summary['queries']==40 and summary['calls']==200 and summary['full_support']==sum(v[key]['full_support'] for v in obs.values()) and summary['total_tokens']==sum(v[key]['tokens'] for v in obs.values()),key)
    require(content(D/'ui-check.json')['browser']['external_requests']==0,'browser evidence');return len(manifest)
if __name__=='__main__': print('Verified files',verify(),'and 160 live packets')

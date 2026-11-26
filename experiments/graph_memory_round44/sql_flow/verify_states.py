"""Independent SQL checks of every positive witness weight and each directional count."""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from common44 import D,load,sha
from operators import ARMS,apply,connect,flags

def main():
    assert sha(D/'normalized.json.gz')==load(D/'fixture-seal.json')['fixture']
    rows=load(D/'normalized.json.gz');tested=0
    with TemporaryDirectory() as tmp:
        dbs={a:connect(Path(tmp)/(a+'.db'),a,True) for a in ARMS}
        for t,tr in enumerate(rows):
            edges=Counter()
            for delta,expected in tr:
                for a,b,w in delta:
                    edges[a,b]+=w
                    if not edges[a,b]: del edges[a,b]
                ep={}
                for (a,b),w in edges.items():
                    ep.setdefault(a,[0,0])[0]+=w
                    ep.setdefault(b,[0,0])[1]+=w
                ref_edges=sorted((a,b,w) for (a,b),w in edges.items())
                ref_ends=sorted((k,*vals) for k,vals in ep.items())
                for arm,db in dbs.items():
                    apply(db,arm,t,delta)
                    assert flags(db,arm,t)==dict(expected)
                    if arm in ('pair','co','scan'):
                        assert db.execute('SELECT a,b,w FROM pair WHERE t=? ORDER BY a,b',(t,)).fetchall()==ref_edges
                    if arm in ('ends','sql_group','co'):
                        assert db.execute('SELECT v,nout,nin FROM endpoint WHERE t=? ORDER BY v',(t,)).fetchall()==ref_ends
                    tested+=1
        for db in dbs.values():db.close()
    print('Verified all weights, counts and flags after',tested,'SQL plan/state transitions')

if __name__=='__main__':main()

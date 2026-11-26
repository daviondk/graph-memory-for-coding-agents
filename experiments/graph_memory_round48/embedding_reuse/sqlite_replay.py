"""Persist each observed encoder key. SQL restricts membership to materialized states with strictly shorter compatible histories."""
from inventory import *
import sqlite3,tempfile,time
def main():
    sig=read(D/'input-seal.json');r=read(D/'inventory.json.gz');p=read(D/'predecessors.json');tok=read(TOK)
    assert sha(TOK)==sig['source'] and sha(D/'predecessors.json')==sig['predecessors']
    lookup={};digests={}
    for q,v in r.items():
        for doc,k in zip(v['docs'],tok['states'][q]['doc']):
            if k not in digests:digests[k]=bytes.fromhex(key(sig['namespace'],tok['tokens'][k][1]))
            i=doc[0];assert i not in lookup or lookup[i]==digests[k];lookup[i]=digests[k]
    assert len(set(lookup.values()))==len(lookup)==sig['keys']
    gold=read(D/'per-state.json.gz')['causal'];scope=bytes.fromhex(sig['namespace']);other=bytes.fromhex(sig['changed_namespace'])
    order=sorted(r,key=lambda q:(r[q]['group'],len(r[q]['hist']),digest('sqlite-order'+q)));index={q:i for i,q in enumerate(order)};record={};started=time.perf_counter()
    # Ordinary rollback journal on local D, removed with this script's own temporary directory after close.
    with tempfile.TemporaryDirectory(dir=CACHE,prefix='r48-key-sql-') as temp:
        path=Path(temp)/'keys.sqlite';db=sqlite3.connect(path)
        try:
            db.executescript('CREATE TABLE observed(state INTEGER, ns BLOB, key BLOB, PRIMARY KEY(state,ns,key)) WITHOUT ROWID; CREATE TEMP TABLE predecessors(state INTEGER PRIMARY KEY); CREATE TEMP TABLE incoming(i INTEGER PRIMARY KEY, key BLOB, tokens INTEGER);')
            pred_query='SELECT COUNT(*), COALESCE(SUM(tokens),0) FROM incoming WHERE EXISTS (SELECT 1 FROM predecessors AS p CROSS JOIN observed AS o WHERE o.state=p.state AND o.ns=? AND o.key=incoming.key)'
            plan=[v[-1] for v in db.execute('EXPLAIN QUERY PLAN '+pred_query,(scope,))]
            for q in order:
                v=r[q];assert all(index[k]<index[q] for k in p[q]);docs=v['docs']
                with db:
                    db.execute('DELETE FROM predecessors');db.execute('DELETE FROM incoming')
                    db.executemany('INSERT INTO predecessors VALUES (?)',[(index[i],) for i in p[q]])
                    db.executemany('INSERT INTO incoming VALUES (?,?,?)',[(i,lookup[t[0]],t[1]) for i,t in enumerate(docs)])
                    hits,tokens=db.execute(pred_query,(scope,)).fetchone();bad=db.execute(pred_query,(other,)).fetchone()
                    assert [hits,tokens]==[gold[q]['prior_docs'],gold[q]['prior_tokens']] and bad==(0,0)
                    db.execute('INSERT OR IGNORE INTO observed SELECT ?,?,key FROM incoming',(index[q],scope))
                    record[q]=[hits,tokens]
            rows=db.execute('SELECT COUNT(*) FROM observed').fetchone()[0];db.commit();disk=path.stat().st_size
        finally:db.close()
    write('sql-rows.json.gz',record);write('sql-audit.json',dict(db_version=sqlite3.sqlite_version,source=sha(D/'input-seal.json'),output=sha(D/'sql-rows.json.gz'),program=sha(Path(__file__)),
         rows=rows,storage_bytes=disk,model_mismatch_hits=0,states=len(r),plan=plan,query=pred_query,elapsed=time.perf_counter()-started,storage_scope='32-byte key and namespace per state; embedding vectors stored separately, excluded'))
    print('Verified actual SQLite index membership over',len(r),'states,',rows,'rows and',disk,'database bytes.')
if __name__=='__main__':main()


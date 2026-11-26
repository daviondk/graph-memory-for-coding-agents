"""Additional physical controls with packed adjacency lists or packed incident IDs."""
from collections import Counter
from codec import blob_counts,blob_ids,counts_blob,ids_blob

EXTRA=('undirected','pairblob','packedlog','packed8')
SCHEMA={
    'undirected':"""CREATE TABLE pair(a INTEGER,b INTEGER,n INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;
                 CREATE INDEX ix_back ON pair(b,a);""",
    'pairblob':"CREATE TABLE packet(a INTEGER PRIMARY KEY,v BLOB NOT NULL);",
    'packedlog':"""CREATE TABLE packet(a INTEGER PRIMARY KEY,v BLOB NOT NULL);
                   CREATE TABLE episode(id INTEGER PRIMARY KEY,v BLOB NOT NULL);""",
    'packed8':"""CREATE TABLE packet(a INTEGER PRIMARY KEY,v BLOB NOT NULL);
                 CREATE TABLE episode(id INTEGER PRIMARY KEY,v BLOB NOT NULL,n INTEGER NOT NULL);""",
}

def write(db,mode,t,nodes,payload):
    if mode=='undirected':
        from itertools import combinations
        db.executemany("INSERT INTO pair VALUES(?,?,1) ON CONFLICT(a,b) DO UPDATE SET n=n+1",combinations(nodes,2))
        return
    if mode=='packedlog':
        db.execute("INSERT INTO episode VALUES(?,?)",(t,payload))
    if mode=='packed8':
        db.execute("INSERT INTO episode VALUES(?,?,?)",(t,payload,len(nodes)))
    for a in nodes:
        row=db.execute("SELECT v FROM packet WHERE a=?",(a,)).fetchone()
        data=row[0] if row else b''
        if mode=='pairblob':
            vals=blob_counts(data)
            for i in nodes:
                if i!=a:vals[i]=vals.get(i,0)+1
            out=counts_blob(vals)
        else:
            events=blob_ids(data)+(t,)
            if mode=='packed8' and len(events)>8:
                victim=events[0]
                events=events[1:]
                refs,=db.execute("UPDATE episode SET n=n-1 WHERE id=? RETURNING n",(victim,)).fetchone()
                if refs==0:db.execute("DELETE FROM episode WHERE id=?",(victim,))
            out=ids_blob(events)
        if out!=data or not row:
            db.execute("INSERT OR REPLACE INTO packet VALUES(?,?)",(a,out))

def evidence(db,mode,a):
    if mode=='undirected':
        return dict(db.execute("""SELECT b,n FROM pair WHERE a=?
                                   UNION ALL SELECT a,n FROM pair WHERE b=?""",(a,a)))
    row=db.execute("SELECT v FROM packet WHERE a=?",(a,)).fetchone()
    if not row:return {}
    if mode=='pairblob':return blob_counts(row[0])
    events=blob_ids(row[0]);scores=Counter()
    for start in range(0,len(events),400):
        chunk=events[start:start+400]
        args=','.join('?' for _ in chunk)
        for data, in db.execute(f'SELECT v FROM episode WHERE id IN ({args})',chunk):
            scores.update(blob_ids(data))
    scores.pop(a,None)
    return scores

def tables(db,mode):
    names=['node','window']+(['pair'] if mode=='undirected' else
                             ['packet'] if mode=='pairblob' else ['episode','packet'])
    if mode=='packed8':
        actual=Counter()
        for v, in db.execute("SELECT v FROM packet"):
            seq=blob_ids(v); assert len(seq)<=8
            actual.update(seq)
        assert dict(actual)==dict(db.execute("SELECT id,n FROM episode"))
    return {n:db.execute('SELECT COUNT(*) FROM '+n).fetchone()[0] for n in names}

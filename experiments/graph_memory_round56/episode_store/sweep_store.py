"""Maintain only the suffix coverage required for each anchor, with optional page-like event blocks."""
from collections import Counter
from codec import blob_ids, ids_blob, record, unpack_events

BLOCK=32
LIMIT=8
MODES=('scanlog','sweepscan','blocklog','blocksweep')
DDL_EVENT='CREATE TABLE episode(t INTEGER PRIMARY KEY,v BLOB NOT NULL);'
DDL_BLOCK='CREATE TABLE block(g INTEGER PRIMARY KEY,mask BLOB NOT NULL,body BLOB NOT NULL);'
DDL={m:(DDL_BLOCK if m.startswith('block') else DDL_EVENT) for m in MODES}

def block_data(items):
    members={i for _,value in items for i in blob_ids(value)}
    return ids_blob(sorted(members)), b''.join(record(offset,value) for offset,value in items)

def add(db,mode,t,nodes,payload):
    if not mode.startswith('block'):
        db.execute('INSERT INTO episode VALUES(?,?)',(t,payload))
        return
    g,offset=divmod(t,BLOCK)
    current=db.execute('SELECT body FROM block WHERE g=?',(g,)).fetchone()
    rows=unpack_events(current[0]) if current else []
    rows.append((offset+1,payload))
    mask,body=block_data(rows)
    db.execute('INSERT OR REPLACE INTO block VALUES(?,?,?)',(g,mask,body))

def keep_event(seen,value):
    ids=blob_ids(value)
    keep=any(seen[a]<LIMIT for a in ids)
    seen.update(ids)
    return keep

def sweep(db,mode):
    seen=Counter()
    if mode=='sweepscan':
        gone=[(t,) for t,value in db.execute('SELECT t,v FROM episode ORDER BY t DESC')
              if not keep_event(seen,value)]
        db.executemany('DELETE FROM episode WHERE t=?',gone)
    elif mode=='blocksweep':
        edits=[]
        for g,raw in db.execute('SELECT g,body FROM block ORDER BY g DESC'):
            items=unpack_events(raw)
            keep=[(o,v) for o,v in reversed(items) if keep_event(seen,v)]
            if len(keep)!=len(items):
                edits.append((g,list(reversed(keep))))
        for g,items in edits:
            if items:
                mask,body=block_data(items)
                db.execute('UPDATE block SET mask=?,body=? WHERE g=?',(mask,body,g))
            else:
                db.execute('DELETE FROM block WHERE g=?',(g,))

def witnesses(db,mode,a):
    """Return actual (commit ordinal, members) for this anchor in reverse order."""
    if a<0:return []
    selected=[]
    if not mode.startswith('block'):
        for t,v in db.execute('SELECT t,v FROM episode ORDER BY t DESC'):
            ids=blob_ids(v)
            if a in ids:
                selected.append((t,ids))
                if len(selected)==LIMIT:break
    else:
        for g,mask in db.execute('SELECT g,mask FROM block ORDER BY g DESC'):
            if a not in blob_ids(mask):continue
            raw,=db.execute('SELECT body FROM block WHERE g=?',(g,)).fetchone()
            for offset,v in reversed(unpack_events(raw)):
                ids=blob_ids(v)
                if a in ids:
                    selected.append((g*BLOCK+offset-1,ids))
                    if len(selected)==LIMIT:return selected
    return selected

def evidence(db,mode,a):
    out=Counter(i for _,ids in witnesses(db,mode,a) for i in ids if i!=a)
    return out

def materialized(db,mode):
    if mode.startswith('block'):
        return {g*BLOCK+offset-1:blob_ids(v) for g,raw in db.execute('SELECT g,body FROM block')
                for offset,v in unpack_events(raw)}
    return {t:blob_ids(v) for t,v in db.execute('SELECT t,v FROM episode')}

def tables(db,mode):
    tab='block' if mode.startswith('block') else 'episode'
    return {n:db.execute('SELECT count(*) FROM '+n).fetchone()[0] for n in ('node','window',tab)}

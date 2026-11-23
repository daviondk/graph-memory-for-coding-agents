"""Freeze the exact E5-prefixed corpus and cross-trajectory keys without gold."""
import hashlib, sqlite3, sys
from project import ROOT,CACHE,W,OFF,load,put,split,audit_ids,pilot,strings
def key(t):return hashlib.sha256(t.encode()).digest()
def db():
    con=sqlite3.connect(CACHE/'vectors.sqlite3',timeout=60)
    con.execute('pragma journal_mode=WAL')
    con.execute('create table if not exists corpus(k blob primary key, text text not null, audit integer not null, nchar integer not null) without rowid')
    con.execute('create table if not exists vectors(k blob, prec text, v blob, primary key(k,prec)) without rowid')
    return con
def inventory():
    con=db(); ids=audit_ids();count=0;occ=0;nodes=0;h=hashlib.sha256()
    paths=sorted((CACHE/'projection').glob('*.json.gz'))
    assert len(paths)==len(set(split().values())),len(paths)
    for p in paths:
        row=load(p);ss=strings(row)
        audit=int(row['t'] in ids)
        con.executemany('insert into corpus(k,text,audit,nchar) values(?,?,?,?) on conflict(k) do update set audit=max(excluded.audit,corpus.audit) where corpus.text=excluded.text',[(key(s),s,audit,len(s)) for s in ss])
        count+=len(row['q']);nodes+=len(row['pool']);occ+=len(ss)
        h.update(p.name.encode()+b'\0'+bytes.fromhex(pilot.sha(p)))
        if count%100==0:con.commit()
    con.commit()
    assert count==len(split())
    n,na,chars=con.execute('select count(*),sum(audit),sum(nchar) from corpus').fetchone()
    put(ROOT/'inventory.json',dict(n_queries=count,n_trajectories=len(paths),candidate_occurrences=nodes,strings_before_dedup=occ,
        unique_prefixed_strings=n,audit_unique_prefixed_strings=na,characters_after_dedup=chars,projection_digest=h.hexdigest(),
        audit_trajectories=sorted(ids),weights=load(OFF.parents[1]/'graph_memory_round17/isetrace/dense/weights-lock.json'),
        files={p.name:pilot.sha(p) for p in [OFF/'cohort.json',OFF/'source-lock.json',OFF/'rank.py',OFF.parents[1]/'graph_memory_round17/isetrace/pilot.py']}))
    print('unique',n,'chars',chars,flush=True)
if __name__=='__main__':inventory()

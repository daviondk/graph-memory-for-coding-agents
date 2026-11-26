"""Consolidate actual six-tenant end states into shared B-trees and check every witness."""
from collections import defaultdict
from pathlib import Path
from statistics import median
import argparse
from time import perf_counter_ns
import random
import sqlite3
import tempfile
from bench import HERE,PANELS,connect,initialize,io,project,update
from codec import blob_ids,unpack_events
from sweeps import PLANS

BASE=("node","window")
SCHEMAS={
    "node":"id INTEGER,path TEXT NOT NULL,f INTEGER NOT NULL,PRIMARY KEY(q,id),UNIQUE(q,path)",
    "window":"t INTEGER,v BLOB NOT NULL,PRIMARY KEY(q,t)",
    "packet":"a INTEGER,v BLOB NOT NULL,PRIMARY KEY(q,a)",
    "block":"g INTEGER,mask BLOB NOT NULL,body BLOB NOT NULL,PRIMARY KEY(q,g)"
}

def original_dbs(panel,mode):
    sets=[];refs=[]
    for repo,stream in io(PANELS[panel]/'commits.json.gz').items():
        rows,_=project(stream)
        db=connect(':memory:');initialize(db,mode)
        by_anchor=defaultdict(list)
        for t,(_,nodes,born,_) in enumerate(rows):
            update(db,mode,0,t,nodes,born)
            for a in nodes:by_anchor[a].append((t,nodes))
        tabs=[*BASE]+(['packet'] if mode=='inline' else ['episode','packet'] if mode=='packed8' else
                     ['block'] if mode.startswith('block') else ['episode'])
        sets.append({tab:list(db.execute('SELECT * FROM '+tab+' ORDER BY 1')) for tab in tabs})
        refs.append({a:v[-8:][::-1] for a,v in by_anchor.items()})
        db.close()
    return sets,refs

def witness(db,mode,q,a):
    if mode=='inline':
        raw,=db.execute('SELECT v FROM packet WHERE q=? AND a=?',(q,a)).fetchone()
        return [(n-1,blob_ids(v)) for n,v in unpack_events(raw)]
    if mode=='packed8':
        raw,=db.execute('SELECT v FROM packet WHERE q=? AND a=?',(q,a)).fetchone()
        seq=blob_ids(raw)
        if not seq:return []
        marks=','.join('?' for _ in seq)
        return [(t,blob_ids(data)) for t,data in db.execute(
            f'SELECT id,v FROM episode WHERE q=? AND id IN ({marks}) ORDER BY id DESC',(q,*seq))]
    out=[]
    if mode.startswith('block'):
        for g,mask in db.execute('SELECT g,mask FROM block WHERE q=? ORDER BY g DESC',(q,)):
            if a not in blob_ids(mask):continue
            body,=db.execute('SELECT body FROM block WHERE q=? AND g=?',(q,g)).fetchone()
            for offset,value in reversed(unpack_events(body)):
                members=blob_ids(value)
                if a in members:
                    out.append((g*32+offset-1,members))
                    if len(out)==8:return out
    else:
        for t,v in db.execute('SELECT id,v FROM episode WHERE q=? ORDER BY id DESC',(q,)):
            members=blob_ids(v)
            if a in members:
                out.append((t,members))
                if len(out)==8:break
    return out

def measure(path,sets,refs,names,mode,page):
    db=sqlite3.connect(path)
    db.execute("PRAGMA page_size="+str(page))
    db.execute("PRAGMA journal_mode=MEMORY")
    schemes={**SCHEMAS,'episode':('id INTEGER,v BLOB NOT NULL,'+('n INTEGER NOT NULL,' if mode=='packed8' else '')+
                                 'PRIMARY KEY(q,id)')}
    sizes=defaultdict(int)
    db.execute('CREATE TABLE space(q INTEGER PRIMARY KEY,name TEXT NOT NULL)')
    for tab in sets[0]:
        db.execute(f'CREATE TABLE {tab}(q INTEGER NOT NULL,'+schemes[tab]+') WITHOUT ROWID')
    for q,tabrows in enumerate(sets):
        db.execute('INSERT INTO space VALUES(?,?)',(q,names[q]))
        for tab,rows in tabrows.items():
            if not rows:continue
            form='INSERT INTO '+tab+' VALUES('+','.join('?' for _ in range(1+len(rows[0])))+')'
            db.executemany(form,[(q,*r) for r in rows])
            sizes[tab]+=sum(len(v) for r in rows for v in r if isinstance(v,bytes))
    db.commit();db.execute('VACUUM');db.close()
    db=sqlite3.connect(path)
    assert db.execute('PRAGMA page_size').fetchone()==(page,)
    assert db.execute('PRAGMA integrity_check').fetchone()==('ok',)
    checked=0
    for q,expected in enumerate(refs):
        for a,target in expected.items():
            assert witness(db,mode,q,a)==target
            checked+=1
    db.close()
    return dict(bytes=path.stat().st_size,witness_lists=checked,blobs=dict(sizes))

def samples(path,mode,refs):
    shared = [(q,a) for q,items in enumerate(refs) for a in sorted(items,key=lambda i:items[i][0][0],reverse=True)[:20]]
    rng = random.Random(56113)
    records=[]
    for block in range(5):
        rng.shuffle(shared)
        totals=[0,0,0]
        for q,a in shared:
            start=perf_counter_ns()
            db=sqlite3.connect(path)
            opened=perf_counter_ns()
            x=witness(db,mode,q,a)
            first=perf_counter_ns()
            y=witness(db,mode,q,a)
            done=perf_counter_ns()
            assert x==y==refs[q][a]
            db.close()
            totals[0]+=opened-start
            totals[1]+=first-opened
            totals[2]+=done-first
        records.append([len(shared),*totals])
    return records

def main(verify,scratch):
    result={}; latency={}
    for panel in PANELS:
        result[panel]={};latency[panel]={}
        with tempfile.TemporaryDirectory(dir=scratch,prefix='r56-six-tenants-') as tmp:
            path=Path(tmp)/'service.sqlite'
            for mode in PLANS:
                sets,refs=original_dbs(panel,mode)
                results={}
                for page in (1024,4096,8192):
                    results[str(page)]=measure(path,sets,refs,list(io(PANELS[panel]/"commits.json.gz")),mode,page)
                    if page==4096 and not verify:latency[panel][mode]=samples(path,mode,refs)
                    path.unlink()
                result[panel][mode]=results
    if verify:assert result==io(HERE/'tenant-results.json')
    else:
        io(HERE/'tenant-results.json',result)
        io(HERE/'tenant-latencies.json.gz',latency)
    for panel,d in result.items():
        print(panel,{m:[v['bytes'] for v in r.values()] for m,r in d.items()})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true')
    p.add_argument('--scratch',type=Path,default=Path('D:/CodexResearch'))
    a=p.parse_args();main(a.verify,a.scratch)

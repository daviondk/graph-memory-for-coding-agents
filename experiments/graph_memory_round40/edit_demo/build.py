"""Project anonymized reader metadata and separate full-snapshot hash witnesses."""
from hashlib import sha256
from pathlib import Path
import argparse
import json
import sqlite3

import pyarrow.parquet as pq

from choose import D, R40, WORK, choose, digest, read


def hash_text(value):
    return sha256(value.encode('utf-8')).hexdigest()


def offsets(lines):
    start=[];end=[];at=0
    for number,line in enumerate(lines):
        start.append(at);at+=len(line.encode('utf8'));end.append(at)
        if number+1!=len(lines):at+=1
    return start,end


def fetch(source, selected):
    manifest=read(source/'files.json')
    need={(s['rid'],s['receipt']):role for role,(s,_,_) in selected.items()}
    found={};run_hashes={};shards={}
    for entry in manifest['events']:
        if not need:break
        p=source/entry['file'];pf=pq.ParquetFile(p)
        for g in range(pf.num_row_groups):
            key=pf.read_row_group(g,columns=['run_id','event_index'])
            hits=[]
            for j,(identity,at) in enumerate(zip(key.column(0).to_pylist(),key.column(1).to_pylist())):
                if identity not in run_hashes:run_hashes[identity]=hash_text(identity)
                pair=run_hashes[identity],at
                if pair in need:hits.append((j,need.pop(pair)))
            if not hits:continue
            assert digest(p)==entry['sha']
            col=pf.read_row_group(g,columns=['event_json']).column(0)
            for j,role in hits:
                obj=json.loads(col[j].as_py())['raw']['observation']
                assert obj['command']=='str_replace' and not obj['is_error']
                found[role]=obj['old_content'],obj['new_content']
                shards[role]=entry['sha']
    assert not need
    return found,shards


def build(out,source):
    out.mkdir(exist_ok=True,parents=True)
    names=('reader.sqlite','witness.sqlite','source-bindings.json')
    if any((out/name).exists() for name in names):raise FileExistsError('Use a fresh output directory')
    selected=choose();views=WORK/'graph_memory_round38/edit_ready'
    manifest=read(views/'manifest.json')['files']
    for name in ('visible.json.gz','input-seal.json'):assert digest(views/name)==manifest[name]
    assert digest(source/'files.json')==read(views/'input-seal.json')['source_manifest']
    seen=read(views/'visible.json.gz')
    pairs,shards=fetch(source,selected)
    db=sqlite3.connect(out/names[0]);grader=sqlite3.connect(out/names[1])
    db.executescript("""
    PRAGMA page_size=4096;
    CREATE TABLE receipt(scenario TEXT PRIMARY KEY, low INTEGER NOT NULL,high INTEGER NOT NULL, line_delta INTEGER NOT NULL, event INTEGER NOT NULL, ack INTEGER NOT NULL);
    CREATE TABLE block(scenario TEXT NOT NULL, unit INTEGER NOT NULL, low INTEGER NOT NULL,high INTEGER NOT NULL,cost INTEGER NOT NULL,gain INTEGER NOT NULL, PRIMARY KEY(scenario,unit)) WITHOUT ROWID;
    """)
    grader.executescript("""
    CREATE TABLE snapshot(scenario TEXT PRIMARY KEY, old_sha TEXT,new_sha TEXT,old_size INTEGER,new_size INTEGER,change_begin INTEGER,change_end INTEGER);
    CREATE TABLE address(scenario TEXT, unit INTEGER,old_start INTEGER,old_end INTEGER,new_start INTEGER,new_end INTEGER, PRIMARY KEY(scenario,unit)) WITHOUT ROWID;
    CREATE TABLE witness(scenario TEXT,unit INTEGER,n INTEGER,new_n INTEGER,seen TEXT,before_sha TEXT,after_sha TEXT, PRIMARY KEY(scenario,unit,n)) WITHOUT ROWID;
    """)
    bindings={}
    for role,(s,blocks,counts) in selected.items():
        before_text,after_text=pairs[role];before,after=before_text.split('\n'),after_text.split('\n')
        old_start,old_end=offsets(before);new_start,new_end=offsets(after);lo,hi,delta=s['start'],s['end'],s['delta']
        assert len(after)-len(before)==delta
        begin=old_start[lo-1];stop=(old_start[hi] if hi<len(before) else old_end[-1])
        grader.execute("INSERT INTO snapshot VALUES(?,?,?,?,?,?,?)",(role,hash_text(before_text),hash_text(after_text),old_end[-1],new_end[-1],begin,stop))
        db.execute("INSERT INTO receipt VALUES(?,?,?,?,?,?)",(role,lo,hi,delta,s['event'],s['receipt']))
        digests={n:h for n,h,_,_ in seen[s['rid']][str(s['view'])]}
        num=bad=old_bad=new_bad=selected_bad=0
        for i,(path,a,b,cost,gain) in enumerate(blocks):
            assert path==s['path'];db.execute("INSERT INTO block VALUES(?,?,?,?,?,?)",(role,i,a,b,cost,gain))
            kept=i in s['eligible'];assert kept==(b<lo or a>hi)
            # Compare the same whole-line envelopes in byte coordinates, including internal LF.
            before_a=old_start[a-1];before_b=old_end[b-1]
            assert kept==(before_b<=begin or before_a>=stop)
            offset=delta if a>hi else 0
            new_a,new_b=(new_start[a+offset-1],new_end[b+offset-1]) if kept else (None,None)
            grader.execute("INSERT INTO address VALUES(?,?,?,?,?,?)",(role,i,before_a,before_b,new_a,new_b))
            if not kept:continue
            for n in range(a,b+1):
                m=n+offset;v=digests[n];p=hash_text(before[n-1]);q=hash_text(after[m-1])
                grader.execute("INSERT INTO witness VALUES(?,?,?,?,?,?,?)",(role,i,n,m,v,p,q))
                num+=1;old_bad+=v!=p;bad+=v!=q;new_bad+=v==p and v!=q
                selected_bad+=i in s['old'] and v!=q
        assert (num,old_bad,bad,new_bad,selected_bad)==tuple(counts.get(k,0) for k in ('lines','prior_mismatch','post_mismatch','new_mismatch','selected_post_mismatch'))
        bindings[role]=dict(run_sha=s['rid'],source_sha=s['path'],event=s['event'],receipt=s['receipt'],shard_sha=shards[role],expected_old=s['old'],expected_new=s['new'],file_reuse=s['file_reuse'],range_reuse=s['range_reuse'],audited_lines=num,prior_mismatch=old_bad,post_mismatch=bad,new_mismatch=new_bad,selected_post_mismatch=selected_bad)
    for c in (db,grader):c.commit();assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok';c.close()
    source_hashes={str(p.relative_to(WORK)).replace('\\','/'):digest(p) for p in (R40/'span_updates/scored.json.gz',R40/'span_updates/audit_strict_rows.json.gz',R40/'natural_invalidations/plans.json.gz',views/'visible.json.gz')}
    out.joinpath(names[2]).write_text(json.dumps(dict(cases=bindings,inputs=source_hashes,corpus_files=digest(source/'files.json')),sort_keys=True,indent=2)+'\n',encoding='utf8')
    print('Projected',len(bindings),'cases and',sum(v['audited_lines'] for v in bindings.values()),'line witnesses')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=D);p.add_argument('--corpus',type=Path,default=Path('D:/CodexResearch/x20-r31-handoff'));args=p.parse_args()
    build(args.out,args.corpus)

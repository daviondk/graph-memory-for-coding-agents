"""Build a field dictionary, normalized visibility and indexed SQL complements."""
from pathlib import Path
from collections import defaultdict
import os
import sys
import gzip
import hashlib
import json
import sqlite3
from time import perf_counter
D=Path(__file__).resolve().parent;W=D.parents[1];R25=W/'graph_memory_round25/directional_open'
PRIVATE=Path('D:/CodexResearch/x20-r28-gap');DB=PRIVATE/'intervals.sqlite'
sys.path.insert(0,str(R25))
import dataset as source
from shared25 import read,save,sha
SQL_LEFT='select l,h from gap indexed by gaps_from_left where ds=? and q=? and e=? and h<=? order by h desc limit 3'
SQL_RIGHT='select l,h from gap where ds=? and q=? and e=? and l>=? order by l limit 3'
MAKE_GAPS="""with bounds(ds,q,e,l,h) as (
    select ds,q,e,0,0 from chosen where e is not null union all
    select ds,q,e,l,h from known union all
    select ds,q,e,n,n from chosen where e is not null),
edges as (select ds,q,e,l,lag(h) over(partition by ds,q,e order by l,h) as previous from bounds)
insert into gap select ds,q,e,previous,l from edges where previous<l"""
def lock():
    base={name:sha(R25/f'{name}-choices.json.gz') for name in ('ise','mdd')}
    for name in base:assert base[name]==read(R25/f'{name}-choice-seal.json')['actions']
    rec={'parents':base,'rule':sha(R25/'direction.py'),'adaptation':sha(R25/'dataset.py'),'prior_address_choice':sha(W/'graph_memory_round23/marginal_open/novelty.py'),'protocol':sha(D/'PROTOCOL_RU.md'),'code':sha(Path(__file__)),'per_side_limit':3,'online_cap':256,'sizes':{'ise':2000,'mdd':661}}
    p=D/'plan.json'
    if p.exists():assert read(p)==rec
    else:assert not (D/'ise-forecasts.json.gz').exists();save(p,rec)
def union(raw):
    ans=[]
    for l,h in sorted(raw):
        if h<=l:continue
        if ans and l<=ans[-1][1]:ans[-1][1]=max(h,ans[-1][1])
        else:ans.append([l,h])
    return ans
def prepare():
    lock();PRIVATE.mkdir(parents=True,exist_ok=True)
    if DB.exists():
        assert (D/'db-receipt.json').exists() and sha(DB)==read(D/'db-receipt.json')['database'];return
    temp=PRIVATE/'intervals-building.sqlite'
    if temp.exists():raise RuntimeError('Existing incomplete database, preserve for inspection and choose a fresh attempt')
    c=sqlite3.connect(temp);start=perf_counter()
    c.executescript("""
        create table fields(ds text,t text,e integer,body text not null,digest text,primary key(ds,t,e)) without rowid;
        create table chosen(ds text,q text,t text,e integer,l integer,h integer,n integer,primary key(ds,q)) without rowid;
        create table known(ds text,q text,e integer,l integer,h integer,primary key(ds,q,e,l)) without rowid;
        create table gap(ds text,q text,e integer,l integer,h integer,primary key(ds,q,e,l)) without rowid;
        create index gaps_from_left on gap(ds,q,e,h desc,l);
    """)
    info={}
    for name in ('ise','mdd'):
        choices=read(R25/f'{name}-choices.json.gz');records=defaultdict(list)
        if name=='ise':reg=source.ro(source.R/'read_causes/registry.sqlite')
        else:docs=source.c.get_views()['documents']
        for q,r in choices.items():records[(r['shard'],r['t'])].append((q,r))
        wanted={}
        for (i,t),rows in records.items():
            if name=='ise':
                raw=read(source.CACHE/f'{i}-{t}.json.gz')['fields'];addrs=dict(reg.execute('select e,eid from address where t=?',(t,)))
            for q,r in rows:
                k=r['cut']
                if not k:c.execute('insert into chosen values(?,?,?,null,null,null,null)',(name,q,str(t)));continue
                e=k['e'];src=raw[addrs[e]] if name=='ise' else docs[e][2]
                assert len(src)==k['L']
                d=hashlib.sha256(src.encode()).hexdigest()
                if (t,e) not in wanted:
                    c.execute('insert into fields values(?,?,?,?,?)',(name,str(t),e,src,d));wanted[t,e]=d
                else:assert wanted[t,e]==d
                known=union([(l,h) for field,l,h in r['base'] if field==e])
                assert [k['l'],k['h']] in known
                c.execute('insert into chosen values(?,?,?,?,?,?,?)',(name,q,str(t),e,k['l'],k['h'],k['L']))
                c.executemany('insert into known values(?,?,?,?,?)',[(name,q,e,l,h) for l,h in known])
        if name=='ise':reg.close()
        info[name]={'questions':len(choices),'source_fields':len(wanted),'groups':len({r['t'] for r in choices.values()})}
    c.execute(MAKE_GAPS);c.commit()
    plans=[list(c.execute('explain query plan '+sql,('ise','q',0,0)))[0][-1] for sql in [SQL_LEFT,SQL_RIGHT]]
    assert 'COVERING INDEX' in plans[0] and 'PRIMARY KEY' in plans[1]
    counts={t:c.execute('select count(*) from '+t).fetchone()[0] for t in ['fields','chosen','known','gap']}
    assert c.execute('pragma integrity_check').fetchone()[0]=='ok';c.close();os.replace(temp,DB)
    save(D/'db-receipt.json',{'database':sha(DB),'bytes':DB.stat().st_size,'SQLite':sqlite3.sqlite_version,'queries':plans,'counts':counts,'inputs':info,'seconds':perf_counter()-start,'plan':sha(D/'plan.json')})
def open_db():return sqlite3.connect(DB.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
if __name__=='__main__':prepare()

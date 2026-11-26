"""Disk-backed flags; every plan includes the same authoritative weighted pairs and reverse index."""
from collections import Counter
from math import isqrt
from pathlib import Path
import sqlite3
import sys
BASE=Path(__file__).resolve().parents[2]/'graph_memory_round44/sql_flow'
sys.path.insert(0,str(BASE))
# Reference file name is also operators.py. Load explicitly to avoid importing this module twice.
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('r44_sql_operators',BASE/'operators.py');ref=module_from_spec(spec);spec.loader.exec_module(ref)

NAMES=('scan','distinct','exact','packed','eager','deferred','exists','scan_memo','exact_memo','deferred_memo')
PACK_WRITE='INSERT INTO aux(t,v,s) VALUES(?,?,?) ON CONFLICT(t,v) DO UPDATE SET s=excluded.s'
PACK_READ='SELECT v,s & 3 FROM aux WHERE t=?'
ORI=('SELECT coalesce(sum(w),0) FROM pair WHERE t=? AND a=?','SELECT coalesce(sum(w),0) FROM pair INDEXED BY pair_in WHERE t=? AND b=?')
HIT=('SELECT 1 FROM pair WHERE t=? AND a=? LIMIT 1','SELECT 1 FROM pair INDEXED BY pair_in WHERE t=? AND b=? LIMIT 1')
def cantor(x,y):
    z=x+y
    return ((z*(z+1)//2+y)<<2) | int(x>0) | (int(y>0)<<1)
def split_cantor(s):
    z=s>>2;w=(isqrt(8*z+1)-1)//2
    y=z-(w*(w+1)//2);return w-y,y
def code(x):return x if x<=3 else -3
def digit(x):return x if x>=0 else 3-x
def signed(x):return x if x<=3 else 3-x
def put_bounded(x,y):return ((7*digit(x)+digit(y))<<2) | int(x!=0) | (int(y!=0)<<1)
def get_bounded(s):
    x,y=divmod(s>>2,7);return signed(x),signed(y)
def net_changes(batch):
    net={}
    for a,b,d in batch:
        net.setdefault(a,[0,0])[0]+=d;net.setdefault(b,[0,0])[1]+=d
    return net

class Reader:
    def __init__(self,db,name):
        self.db=db;self.name=name;self.base=name.removesuffix('_memo');self.memo=name.endswith('_memo')
        self.last=None;self.saved=None;self.n_queries=0;self.n_hits=0;self.max_rows=0
    def empty_cache(self):self.last=None;self.saved=None
    def packed_update(self,t,batch):
        rows=[];deleted=[];db=self.db;base=self.base
        for v,(dx,dy) in net_changes(batch).items():
            if dx==0 and dy==0:continue
            previous=db.execute('SELECT s FROM aux WHERE t=? AND v=?',(t,v)).fetchone()
            old=0 if previous is None else previous[0]
            if base=='packed':
                x,y=split_cantor(old);new=cantor(x+dx,y+dy)
            elif base=='exists':
                new=old
                for j,d in enumerate((dx,dy)):
                    if d<0:
                        self.n_queries+=1
                        if db.execute(HIT[j],(t,v)).fetchone() is None:new&=~(1<<j)
                    elif d>0:new|=1<<j
            else:
                pair=list(get_bounded(old))
                for j,d in enumerate((dx,dy)):
                    if not d:continue
                    before=pair[j]
                    if before>=0:pair[j]=code(before+d)
                    else:
                        lower=-before+d
                        if lower<=0 or (base=='eager' and d<0):
                            self.n_queries+=1
                            pair[j]=code(db.execute(ORI[j],(t,v)).fetchone()[0])
                        else:pair[j]=-min(3,lower)
                new=put_bounded(*pair)
            if old==new:continue
            if new:rows.append((t,v,new))
            else:deleted.append((t,v))
        if rows:db.executemany(PACK_WRITE,rows)
        if deleted:db.executemany('DELETE FROM aux WHERE t=? AND v=?',deleted)
    def apply(self,t,batch):
        db=self.db;db.execute('BEGIN')
        if batch:
            self.empty_cache()
            ref.pair_update(db,t,batch)
            if self.base=='exact':ref.end_update(db,t,batch)
            elif self.base not in ('scan','distinct'):self.packed_update(t,batch)
        db.execute('COMMIT')
    def read(self,t):
        if self.memo and self.last==t:
            self.n_hits+=1
            return self.saved.copy()
        if self.base in ('scan','distinct'):
            result=ref.flags(self.db,'pair' if self.base=='distinct' else 'scan',t)
        elif self.base=='exact':result=dict(self.db.execute(ref.END_READ,(t,)))
        else:result=dict(self.db.execute(PACK_READ,(t,)))
        if self.memo:
            self.last=t;self.saved=result.copy();self.max_rows=max(self.max_rows,len(result))
        return result

def make(path,name,create=True):
    db=sqlite3.connect(path,isolation_level=None)
    if create:db.execute('PRAGMA page_size=4096')
    assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
    for v in ('synchronous=NORMAL','cache_size=-16384','wal_autocheckpoint=0','temp_store=MEMORY','mmap_size=0'):db.execute('PRAGMA '+v)
    if create:
        db.executescript(ref.PAIR_SCHEMA);typ=name.removesuffix('_memo')
        if typ=='exact':db.executescript(ref.END_SCHEMA)
        if typ not in ('scan','distinct','exact'):db.execute('CREATE TABLE aux(t INTEGER,v INTEGER,s INTEGER NOT NULL,PRIMARY KEY(t,v)) WITHOUT ROWID')
    return Reader(db,name)


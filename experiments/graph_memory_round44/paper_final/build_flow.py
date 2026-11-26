"""Extract three public execution histories into anonymous signed witness changes."""
import collections,hashlib,json,sqlite3,sys
from pathlib import Path
D=Path(__file__).resolve().parent;W=D.parents[1]
sys.path.insert(0,str(D.parent/'flow_view'))
import flow
CASE_NAMES=('withdrawn','overlap','accumulating')
def build():
    sh=0;rank=flow.read(D.parent/'flow_view'/f'trace-{sh}.json.gz')
    def best(key,remaining):
        return sorted(remaining,key=lambda t:(-key(rank[t]['counts']),t))[0]
    pool={t for t,v in rank.items() if 6<=v['counts']['boundaries']<=42}
    picks={}
    for name,key in zip(CASE_NAMES,[
            lambda c:c['stale_flags_monotone'],
            lambda c:min(c['adds']-c['retracts'],c['retracts']),
            lambda c:(c['adds'] if c['retracts']==0 else -100000)]):
        item=best(key,pool);picks[item]=name;pool.remove(item)
    pilot=flow.native.api.pilot;tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    def has(text):return bool(pilot.token_chunks(text,tokenizer=tok,max_tokens=504,overlap_tokens=64))
    dbpath=D/'apps/flow/flow.sqlite'
    db=sqlite3.connect(':memory:')
    db.executescript("""
      CREATE TABLE scenario(id TEXT PRIMARY KEY,n INTEGER,focus INTEGER,trace TEXT) WITHOUT ROWID;
      CREATE TABLE delta(case_id TEXT,step INTEGER,idx INTEGER,src INTEGER,dst INTEGER,weight INTEGER,PRIMARY KEY(case_id,step,idx)) WITHOUT ROWID;
      CREATE TABLE expected(case_id TEXT,step INTEGER,digest TEXT,PRIMARY KEY(case_id,step)) WITHOUT ROWID;
    """)
    for _,row in pilot.stream(flow.native.api.RAW/f'trajectories-{sh:05d}.jsonl'):
        t=row['session_id']
        if t not in picks:continue
        case=picks[t];tr=flow.native.adapt_isetrace_record(flow.native.parse_isetrace_record(row),source_revision=pilot.RAW[1])
        steps,ref,names,counts=flow.extract(tr.events,has);focus=1
        last={};peak=-1;ever={}
        for j,(batch,truth) in enumerate(zip(steps,ref),1):
            db.executemany('insert into delta values(?,?,?,?,?,?)',[(case,j,i,a,b,s) for i,(a,b,s) in enumerate(sorted(batch,key=lambda x:(x[0],x[1],-x[2])))])
            f={}
            for a,b in truth:
                f[a]=f.get(a,0)|1;f[b]=f.get(b,0)|2
            lost=sum((v&~f.get(i,0)).bit_count() for i,v in last.items());ever={k:v|ever.get(k,0) for k,v in (ever|f).items()}
            metric=lost if case=='withdrawn' else (sum(v<0 for a,b,v in batch) if case=='overlap' else len(f))
            if metric>peak:focus=j;peak=metric
            last=f
            bs=json.dumps(sorted(f.items()),separators=(',',':')).encode()
            db.execute('insert into expected values(?,?,?)',(case,j,hashlib.sha256(bs).hexdigest()))
        db.execute('insert into scenario values(?,?,?,?)',(case,len(steps),focus,t))
    assert db.execute('select count(*) from scenario').fetchone()[0]==3
    db.commit()
    tmp=dbpath.with_suffix('.new')
    if tmp.exists():raise RuntimeError('Existing partial build')
    copy=sqlite3.connect(tmp);db.backup(copy);copy.close();db.close();tmp.replace(dbpath)
if __name__=='__main__':build()

"""Generate a text store containing only exact, retained block strings and questions."""
from pathlib import Path
import gzip,hashlib,json,sqlite3,sys,time
ROOT=Path(__file__).resolve().parent;SER=ROOT.parent;TR=SER/'trained_rank'
sys.path.insert(0,str(TR))
from prepare import load,put,pilot
RUN=Path('D:/CodexResearch/x20-isetrace-bounded-dense')
WR=SER/'write_learned';ON=SER/'online_write';DE=SER/'write_transfer'
ARMS=('full','output_head','fifo')
def key(s):return hashlib.sha256(s.encode('utf8')).digest()
def db():
    c=sqlite3.connect(RUN/'blocks.sqlite3',timeout=90)
    c.execute('pragma journal_mode=WAL')
    c.execute('create table if not exists inputs(k blob primary key, txt text not null, nc int not null) without rowid')
    c.execute('create table if not exists vectors(k blob primary key, v blob not null) without rowid')
    return c
def stream(p):
    with gzip.open(p,'rb') as f:
        for line in f:yield json.loads(line)
def record(stage,i):
    if stage=='test':return ON/f'forecast-{i}.jsonl.gz',WR/f'forecast-{i}.jsonl.gz',Path('D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection')
    return DE/f'predictions-{i}.jsonl.gz',WR/f'transfer-dev-{i}.jsonl.gz',Path('D:/CodexResearch/x20-isetrace-runtime/write-dev-private/projection')
def prepare():
    c=db();files={};nq={};stat={}
    for st in ['test','dev']:
        nq[st]=0
        for i in range(8):
            base,lear,pro=record(st,i)
            # Recheck that the exact source-only artifacts were sealed before this run.
            manifests=[(ON if st=='test' else DE)/'MANIFEST_SHA256.json',WR/'MANIFEST_SHA256.json']
            for path,man in zip([base,lear],manifests):
                assert load(man)[path.name]==pilot.sha(path)
                files[str(path.relative_to(SER)).replace(chr(92),'/')]=pilot.sha(path)
            cards=[]
            for r,w in zip(stream(base),stream(lear),strict=True):
                t=r['t'];assert t==w['t']
                proj=load(pro/f'{i}-{t}.json.gz');addresses=r['addresses'];blocks=r['blocks'];fields=proj['fields']
                keep={};reads={}
                for a in ARMS:
                    if a=='full':data=w['a']['tokens/full']
                    else:data=r['arms'][a+'/8192']
                    keep[a],reads[a]=data[0],data[1]
                    assert sum(blocks[j][3] for j in keep[a])<=8192
                    assert all(set(ids)<=set(keep[a]) for ids in reads[a].values())
                add={};compact={};qrows=[]
                for j in sorted(set.union(*(set(x) for x in keep.values()))):
                    e,start,end,cost,nbytes=blocks[j];eid,ptr=addresses[e]
                    raw=fields[eid][start:end]
                    assert len(raw.encode())==nbytes and cost>0
                    s='passage: '+raw;k=key(s);add[k]=s;compact[j]=[eid,ptr,start,end,cost,nbytes,k.hex()]
                for q,txt in proj['q']:
                    s='query: '+txt;k=key(s);add[k]=s;qrows.append([q,k.hex()])
                c.executemany('insert or ignore into inputs values(?,?,?)',[(k,s,len(s)) for k,s in add.items()])
                cards.append(dict(t=t,b=compact,k=keep,q=qrows,bm=reads));nq[st]+=len(qrows)
            c.commit();dest=RUN/f'cards-{st}-{i}.json.gz';put(dest,cards);files[dest.name]=pilot.sha(dest)
    assert nq=={'test':2000,'dev':580}
    n,chars=c.execute('select count(*),sum(nc) from inputs').fetchone()
    put(ROOT/'index-plan.json',dict(inputs=files,n_queries=nq,unique_strings=n,characters=chars,trained=pilot.sha(TR/'trained-checkpoint.json'),
        protocol=pilot.sha(ROOT/'PROTOCOL_RU.md'),source_code=pilot.sha(ROOT/'inputs.py')))
    print(n,chars,nq,flush=True)
if __name__=='__main__':prepare()

"""Paired workload in file-backed SQLite; retain per-trajectory times, physical ledgers and one set of final databases."""
from hashlib import sha256
import gzip,json,os,platform,random,sqlite3,sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns as wall,process_time_ns as cpu
from operators import NAMES,BASE,make

D=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def save(p,z):
    b=(json.dumps(z,sort_keys=True,separators=(',',':'))+'\n').encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix=='.gz' else b)
def sha(p):return sha256(p.read_bytes()).hexdigest()
FIELDS=['wall','cpu','write','read','probes','cache_hits']
def freeze():
    r45=BASE.parents[1]/'graph_memory_round45/bounded_counts'
    d={'protocol':sha(D/'PROTOCOL_RU.md'),'operators':sha(D/'operators.py'),'runner':sha(Path(__file__)),'reference':sha(BASE/'operators.py'),
       'fixture':sha(BASE/'normalized.json.gz'),'parent_checks':sha(r45/'checks.json'),'arms':list(NAMES),'fields':FIELDS,'bootstrap_seed':460131,
       'design':[[1,4],[4,1],[1,4]],'sqlite':sqlite3.sqlite_version,'python':platform.python_version(),'platform':platform.platform()}
    f=D/'registration.json'
    if not f.exists():save(f,d)
    assert read(f)==d
    return d
def storage(engine,path):
    db=engine.db
    space_before=sum(f.stat().st_size for f in (path,path.with_name(path.name+'-wal'),path.with_name(path.name+'-shm')) if f.exists())
    wal=path.with_name(path.name+'-wal').stat().st_size;shm=path.with_name(path.name+'-shm').stat().st_size
    a=wall();assert db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()==(0,0,0);checkpoint=wall()-a
    objs=db.execute('select name,count(*),sum(pgsize),sum(payload),sum(unused) from dbstat group by name order by name').fetchall()
    ps=db.execute('PRAGMA page_size').fetchone()[0];nf=db.execute('PRAGMA freelist_count').fetchone()[0]
    assert sum(row[2] for row in objs)+nf*ps==path.stat().st_size
    size=path.stat().st_size
    exact=db.execute('select count(*),sum(w),min(w) from pair').fetchone();assert exact[-1]>0
    a=wall();db.close();closing=wall()-a
    return dict(file=size,objects=objs,wal=wal,shm=shm,before_checkpoint_total=space_before,checkpoint_ns=checkpoint,close_ns=closing,pair_population=exact,max_cache_rows=engine.max_rows)
def execute(fixture,k,rep):
    rng=random.Random(460230+61*rep+k)
    records={a:[] for a in NAMES};stats={}
    with TemporaryDirectory(dir=D) as tmp:
        root=Path(tmp);paths={a:root/(a+'.sqlite') for a in NAMES}
        engines={a:make(p,a) for a,p in paths.items()}
        terminals=[]
        for t,frames in enumerate(fixture):
            stream=[(changes,dict(wanted)) for changes,wanted in frames];terminals.append(stream[-1][1])
            order=list(NAMES);rng.shuffle(order)
            for arm in order:
                reader=engines[arm];w=r=0;q0=reader.n_queries;h0=reader.n_hits;start=wall();pc=cpu()
                for delta,target in stream:
                    a=wall();reader.apply(t,delta);w+=wall()-a
                    for j in range(k):
                        a=wall();got=reader.read(t);r+=wall()-a
                        if got!=target:raise ValueError((arm,t,j,'wrong flags'))
                elapsed_cpu=cpu()-pc;elapsed_wall=wall()-start
                records[arm].append([elapsed_wall,elapsed_cpu,w,r,reader.n_queries-q0,reader.n_hits-h0])
        for arm,path in paths.items():
            stats[arm]=storage(engines[arm],path)
            start=wall();fresh=make(path,arm,False)
            for t,target in enumerate(terminals):assert fresh.read(t)==target
            stats[arm]['reopen_and_scan_ns']=wall()-start
            assert fresh.db.execute('pragma quick_check').fetchone()==('ok',);fresh.db.close()
            if rep==0 and k==1 and not arm.endswith('_memo'):
                target=D/(arm+'.sqlite')
                if target.exists():raise FileExistsError(target)
                os.rename(path,target)
    return {'records':records,'storage':stats,'rep':rep,'reads':k}
def main():
    with sqlite3.connect(':memory:') as trial:trial.execute('select count(*) from dbstat').fetchone()
    reg=freeze();fixture=read(BASE/'normalized.json.gz')
    assert len(fixture)==1207 and sum(map(len,fixture))==31279
    for rep,seq in enumerate(reg['design']):
        for k in seq:
            p=D/f'run-{rep}-{k}.json.gz'
            if p.exists():raise FileExistsError(p)
            start=wall();res=execute(fixture,k,rep);res['elapsed_ns']=wall()-start;save(p,res)
            print('completed',rep,k,round(res['elapsed_ns']/1e9,2),flush=True)
    save(D/'run-seal.json',{'registration':sha(D/'registration.json'),'runs':{f.name:sha(f) for f in sorted(D.glob('run-*.json.gz'))}})
if __name__=='__main__':main()


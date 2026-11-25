"""Run compiled C++ operators and bind typed binary state to the same SQLite C engine."""
import ctypes as ct
import os,random,shutil,sqlite3,struct,subprocess,sys,time
import bench as b
from bench import g,np,D,PRIVATE
CAS=("random1","selected1","random8","random32","all")
MODES=("rebuild","cost_certificate","interval_certificate","repair")
fmt=struct.Struct("<d5i4x")
def blob(rows):return b"".join(fmt.pack(*v) for v in rows)
def ptr(rows):return ct.create_string_buffer(blob(rows))
def main():
    cc=shutil.which("g++");runtime=b.Path(sys.base_prefix)/"DLLs/sqlite3.dll";assert cc and runtime.exists()
    flags=["-O3","-std=c++17","-ffp-contract=off","-shared","-static-libstdc++","-static-libgcc"]
    cpp=D/"cached_packing.cpp";dll=PRIVATE/("cached-"+b.sha(cpp)[:16]+".dll")
    if not dll.exists():subprocess.run([cc,*flags,str(cpp),str(runtime),"-o",str(dll)],check=True)
    handles=[os.add_dll_directory(str(p)) for p in (runtime.parent,b.Path(cc).parent)]
    api=ct.CDLL(str(dll));api.packing_open.argtypes=[ct.c_char_p];api.packing_open.restype=ct.c_void_p
    api.packing_close.argtypes=[ct.c_void_p];api.packing_close.restype=None
    api.packing_run.argtypes=[ct.c_void_p,ct.c_int,ct.c_int,ct.c_int,ct.c_void_p,ct.c_int,ct.c_void_p,ct.c_void_p,ct.c_int,ct.c_void_p,ct.c_void_p];api.packing_run.restype=ct.c_int
    path=PRIVATE/"native.sqlite"
    if not path.exists():shutil.copyfile(b.DB,path)
    db=b.connection(path);db.execute("create table if not exists packed(q integer,budget integer,body blob,primary key(q,budget)) without rowid")
    raw=b.fixture();jobs=[];maxn=0;st=time.perf_counter();db.execute("begin immediate")
    for i,r in enumerate(raw):
        initial=[g.row(v) for v in r["items"]];maxn=max(maxn,len(initial))
        chosen=g.greedy(initial,r["core"],2048)
        db.execute("insert or ignore into packed values(?,?,?)",(i,2048,blob(chosen)))
        assert db.execute("select body from packed where q=? and budget=2048",(i,)).fetchone()[0]==blob(chosen)
        core=ptr([(0.,-1,*v[1:]) for v in r["core"]])
        for case in CAS:
            mut=g.changes(r["items"],chosen,case,r["q"],2048);patch={v[1]:v for v in initial}
            for _,v in mut:patch[v[1]]=v
            final=g.greedy(patch.values(),r["core"],2048);want=[v[1] for v in final]
            jobs.append((i,case,core,len(r["core"]),ptr([x for x,_ in mut]),ptr([y for _,y in mut]),len(mut),want))
    db.execute("commit");db.execute("pragma wal_checkpoint(truncate)")
    storage=list(db.execute("select sum(pgsize),sum(payload) from dbstat where name='packed'").fetchone());db.close()
    b.save(D/"native-build.json",{"cpp_sha":b.sha(cpp),"binary_sha":b.sha(dll),"bin":dll.name,"compiler":subprocess.check_output([cc,"--version"],text=True).splitlines()[0],"flags":flags,
        "runtime_sha":b.sha(runtime),"sqlite":sqlite3.sqlite_version,"binary_cache_2048_bytes":storage,"block_bytes":fmt.size,"prep_seconds_inc_reference":time.perf_counter()-st,
        "prereg":b.sha(D/"NATIVE_PROTOCOL_RU.md"),"wrapper":b.sha(b.Path(__file__))})
    conn=api.packing_open(str(path).encode());assert conn
    rng=random.Random(29);outbuf=np.empty(maxn,dtype=np.int32);obs=np.empty(7,dtype=np.int64);rows=[]
    try:
        for rep in range(8):
            rng.shuffle(jobs)
            for i,case,core,ncore,old,new,n,want in jobs:
                methods=list(enumerate(MODES));rng.shuffle(methods)
                for m,name in methods:
                    tic=time.perf_counter_ns()
                    count=api.packing_run(conn,m,i,2048,core,ncore,old,new,n,outbuf.ctypes.data,obs.ctypes.data)
                    wall=time.perf_counter_ns()-tic
                    assert count>=0 and outbuf[:count].tolist()==want,(i,case,name)
                    if rep:rows.append([rep,i,case,name,*obs.tolist(),wall])
            print("native pass",rep,flush=True)
    finally:api.packing_close(conn)
    b.save(D/"native-times.json.gz",rows)
    b.save(D/"native-check.json",{"comparisons":8*len(jobs)*len(MODES),"timed":len(rows),"mismatches":0,"format":["rep","i","case","method","write_ns","wall_inside_ns","rows","vm","cache_hits","cache_misses","branch","wall_external_including_rollback_ns"],"build":b.sha(D/"native-build.json"),"times":b.sha(D/"native-times.json.gz")})
    assert handles
if __name__=="__main__":main()


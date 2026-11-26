"""Measure actual SQLite calls for full, compressed, split, and approximate priors."""
import contextlib,random,sqlite3,tempfile,time,zlib,statistics
from collections import Counter,defaultdict
from run import HERE,SEEDS,read,put,hashfile,histories
from lossless import pack,Head,batch,np,exact,json,prefix
PRIVATE=__import__("pathlib").Path("D:/CodexResearch/x20-r33-precision")
MODES=("fp64","fp32_approx","zlib","plain_batch","class_batch","class_sequential")

def measure():
    PRIVATE.mkdir(exist_ok=True)
    all_ids=read(HERE/"rows.json.gz")
    panel=sorted(all_ids,key=lambda q:__import__("hashlib").sha256(("r33-physical-prior/"+q).encode()).digest())[:256]
    put(HERE/"physical-plan.json",{"program":hashfile(HERE/"physical.py"),"codec":hashfile(HERE/"lossless.py"),"protocol":hashfile(HERE/"LOSSLESS_PROTOCOL_RU.md"),"panel":panel,"upstream":hashfile(HERE/"results.json")})
    all_modes=defaultdict(Counter);timed=[];cases=[];storage={};rowlog={}
    with tempfile.TemporaryDirectory(dir=PRIVATE) as temp,contextlib.ExitStack() as stack:
        from pathlib import Path
        files={n:Path(temp)/(n+".sqlite") for n in ("fp64","fp32","zlib","plain","class","cold")}
        db={n:stack.enter_context(contextlib.closing(sqlite3.connect(p))) for n,p in files.items()}
        for c in db.values():c.execute("create table t(id integer primary key, data blob not null)")
        ix=0
        for sh in range(8):
            for t,index,costs,queries in histories(sh):
                values=index.raw;plain,cold=pack(values,False);hot,tail=pack(values,True)
                assert cold==tail
                blobs={"fp64":values.astype("<f8").tobytes(),"fp32":values.astype("<f4").tobytes(),"zlib":zlib.compress(values.astype("<f8").tobytes()),"plain":plain,"class":hot,"cold":tail}
                for n,p in blobs.items():db[n].execute("insert into t values(?,?)",(ix,p))
                head=Head(hot);simple=Head(plain)
                assert np.array_equal(head.top,simple.top)
                recon=np.array([head.recover(i,tail[i*5:i*5+5]) for i in range(len(costs))])
                assert recon.tobytes()==values.tobytes()
                storage[t]={"sizes":{n:len(v) for n,v in blobs.items()},"dictionary":int(bool(hot[0]))}
                for q,seed,order,signal,target in queries:
                    def get_raw(ids):return {int(i):tail[i*5:i*5+5] for i in ids}
                    pred,count=batch(head,order,signal,costs,get_raw)
                    seq,reads=exact("lossless",head,order,signal,costs,None,lambda j:head.recover(j,tail[j*5:j*5+5]))
                    approx=prefix(order[np.argsort(-(signal+values.astype(np.float32)[order].astype(float)),kind="stable")],costs)
                    assert pred==seq==target,(q,seed)
                    rowlog.setdefault(q,{})[str(seed)]=[count,reads[1],int(approx==target)]
                    if seed==13 and q in panel:cases.append((ix,order,signal,costs,target,q))
                ix+=1
        for n,c in db.items():
            c.commit();c.execute("vacuum");assert c.execute("pragma integrity_check").fetchone()==("ok",);c.close()
            db[n]=stack.enter_context(contextlib.closing(sqlite3.connect(files[n].as_uri()+"?mode=ro&immutable=1",uri=True)))
        assert len(cases)==len(panel)
        for rep in range(8):
            sequence=[(case,m) for case in cases for m in MODES];random.Random(1881+rep).shuffle(sequence)
            for (ix,order,signal,costs,target,q),m in sequence:
                start=time.perf_counter_ns()
                table=m.split("_")[0];hot=db[table].execute("select data from t where id=?",(ix,)).fetchone()[0];total=len(hot);calls=1
                if table in ("fp32","fp64","zlib"):
                    raw=zlib.decompress(hot) if table=="zlib" else hot
                    prior=np.frombuffer(raw,dtype="<f4" if table=="fp32" else "<f8")
                    picked=prefix(order[np.argsort(-(signal+prior[order]),kind="stable")],costs)
                else:
                    head=Head(hot)
                    def fetch(ids):
                        nonlocal total,calls
                        calls+=1;total+=5*len(ids)
                        return dict(db["cold"].execute("select j.value, substr(t.data,5*j.value+1,5) from t, json_each(?) as j where t.id=?",(json.dumps(ids.tolist()),ix)))
                    def get_one(node):
                        nonlocal total,calls
                        calls+=1;total+=5
                        b=db["cold"].execute("select substr(data,?,5) from t where id=?",(5*node+1,ix)).fetchone()[0]
                        return head.recover(node,b)
                    if m.endswith("batch"):picked,_=batch(head,order,signal,costs,fetch)
                    else:picked,_=exact("lossless",head,order,signal,costs,None,get_one)
                elapsed=time.perf_counter_ns()-start
                assert m=="fp32_approx" or picked==target
                if rep:timed.append([q,m,rep,elapsed,calls,total,int(picked==target)])
        physical={k:p.stat().st_size for k,p in files.items()}
    put(HERE/"lossless-rows.json.gz",rowlog);put(HERE/"lossless-storage.json.gz",storage);put(HERE/"physical-reads.json.gz",timed)
    summary={}
    for m in MODES:
        a=[r for r in timed if r[1]==m];groups=defaultdict(list)
        for r in a:groups[r[0]].append(r[3]/1000)
        med=[statistics.median(x) for x in groups.values()]
        summary[m]={"p50_us":statistics.median(med),"p95_us":np.quantile(med,.95),"mean_sql":statistics.mean(r[4] for r in a),"mean_payload":statistics.mean(r[5] for r in a)}
    rows=np.array([v for r in rowlog.values() for v in r.values()])
    put(HERE/"physical-results.json",{"db":physical,"payload":{k:sum(v["sizes"][k] for v in storage.values()) for k in physical},"dictionary_eligible":sum(v["dictionary"] for v in storage.values()),
        "requests":len(rows),"batched_exact_values":int(rows[:,0].sum()),"sequential_exact_values":int(rows[:,1].sum()),"batch_without_refine":int((rows[:,0]==0).sum()),
        "fp32_ordered":int(rows[:,2].sum()),"timed_calls":len(timed),"timings":summary})
if __name__=="__main__":measure()

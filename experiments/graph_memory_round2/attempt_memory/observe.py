import ast,collections,concurrent.futures,ctypes,itertools,json,os,subprocess,sys
from ctypes import wintypes
from prepare import HERE,OLD,read,save,sha
sys.path.append(str(OLD))
from runner import Info

def changes(v):
    if type(v) is bool:return [not v]
    if type(v) is int:return [v+1,v-1,0,1]
    if type(v) is float:return [v+0.5,v-0.5,1.0]
    if type(v) in (list,tuple,str):
        opts=[v[:-1],v[1:],v[::-1],v[:1],v+v[:1]]
        if v and isinstance(v,(list,tuple)):
            for val in changes(v[0])[:3]:
                opts.append(type(v)([val,*v[1:]]))
        return opts
    if isinstance(v,dict):
        return [dict(list(v.items())[:-1]),{}]
    return []

def probes(row):
    originals={repr(tuple(ast.literal_eval(s))) for s in row["public_args"]}
    new={}
    for s in sorted(originals):
        args=ast.literal_eval(s)
        for i,v in enumerate(args):
            for w in changes(v):
                arglist=list(args);arglist[i]=w
                val=repr(tuple(arglist))
                # Bound inputs and past-derived probes; omit original examples.
                if val not in originals and len(val)<=220:new[val]=None
        for j,k in itertools.combinations(range(len(args)),2):
            if type(args[j])==type(args[k]):
                arglist=list(args);arglist[j],arglist[k]=arglist[k],arglist[j]
                val=repr(tuple(arglist))
                if val not in originals and len(val)<=220:new[val]=None
    return sorted(new,key=lambda s:sha("probe|"+str(row["id"])+"|"+s))[:16]

def execute(d):
    proc=subprocess.Popen([sys.executable,"-W","ignore","-B","-I","-S",str(HERE/"capture_worker.py")],cwd=HERE,
                          stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    k=ctypes.windll.kernel32;k.CreateJobObjectW.restype=wintypes.HANDLE
    k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];k.CloseHandle.argtypes=[wintypes.HANDLE]
    job=k.CreateJobObjectW(None,None)
    try:
        info=Info();info.limits.flags=0x2100;info.process_mem=192*1024*1024
        assert job and k.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) and k.AssignProcessToJobObject(job,int(proc._handle))
        try:
            raw,_=proc.communicate(json.dumps(d).encode(),timeout=5)
            return json.loads(raw.splitlines()[-1])
        except (subprocess.TimeoutExpired,ValueError,IndexError) as exc:
            return {"state":"process:"+type(exc).__name__,"public":False,"vec":[None]*len(d["probes"])}
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        if job:k.CloseHandle(job)

def one(row):
    probe=probes(row);point={k:row[k] for k in ("id","panel","entry","sig","spec")}
    point["probes"]=probe;point["arms"]=[];cache={}
    for j in range(3):
        p=HERE/"programs"/str(row["id"])/f"{j}.py"
        digest=sha(p.read_bytes())
        if digest not in cache:
            d={k:row[k] for k in ("entry","imports","public_assert")};d.update(file=str(p),probes=probe)
            cache[digest]=execute(d)
        point["arms"].append({**cache[digest],"code_sha":digest,"j":j})
    return point
def main():
    its=read(HERE/"inputs.json");panel=sys.argv[1]
    rows=[r for r in its if r["panel"]==panel]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        observed=list(pool.map(one,rows))
    save(HERE/("observed_"+panel+".json"),observed)
    print(panel,len(observed),"candidate states",collections.Counter(a["state"] for row in observed for a in row["arms"]),flush=True)
if __name__=="__main__":main()


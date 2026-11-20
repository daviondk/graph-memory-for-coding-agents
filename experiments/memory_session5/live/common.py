import hashlib,json,pathlib,gzip,os,subprocess,sys,ctypes
from ctypes import wintypes
ROOT=pathlib.Path(__file__).resolve().parent
def digest(x):
    return hashlib.sha256(x if isinstance(x,bytes) else x.encode('utf8')).hexdigest()
def stable(v):return json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(',',':'))
def save(path,obj):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);raw=stable(obj).encode()
    q=p.with_suffix(p.suffix+'.tmp');q.write_bytes(gzip.compress(raw,mtime=0) if p.suffix=='.gz' else raw);os.replace(q,p)
def read(path):
    p=ROOT/path;b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def corpus():return {r['task_id']:r for ln in (ROOT/'dataset.jsonl').read_text(encoding='utf8').splitlines() if (r:=json.loads(ln))}
def src(r):return r['declaration']+r['buggy_solution']
def lines(s):return s.splitlines()
def numbered(s,ids=None):
    items=lines(s);ids=ids if ids is not None else range(1,len(items)+1)
    return '\n'.join(f'{j}|{items[j-1]}' for j in ids)
def slug(i):return i.replace('/','-')
def run_suite(path,entry,suite):
    if not suite.strip():return {'status':'no_examples'}
    payload=json.dumps({'path':str(path),'entry':entry,'suite':suite}).encode()
    # Windows job caps child memory. The child blocks waiting for its stdin before executing candidate code.
    proc=subprocess.Popen([sys.executable,'-I','-S',str(ROOT/'worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=path.parent)
    job=None
    try:
        if os.name=='nt':
            k=ctypes.windll.kernel32
            class Limits(ctypes.Structure):
                _fields_=[('user',ctypes.c_int64),('job',ctypes.c_int64),('flags',wintypes.DWORD),('mi',ctypes.c_size_t),('ma',ctypes.c_size_t),('active',wintypes.DWORD),('aff',ctypes.c_size_t),('priority',wintypes.DWORD),('sched',wintypes.DWORD)]
            class Info(ctypes.Structure):
                _fields_=[('limits',Limits),('io',ctypes.c_uint64*6),('process_mem',ctypes.c_size_t),('job_mem',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
            k.CreateJobObjectW.restype=wintypes.HANDLE
            k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
            k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];k.CloseHandle.argtypes=[wintypes.HANDLE]
            job=k.CreateJobObjectW(None,None);info=Info();info.limits.flags=0x2100;info.process_mem=192*1024*1024
            assert job and k.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info))
            assert k.AssignProcessToJobObject(job,int(proc._handle))
        out,_=proc.communicate(payload,timeout=5)
        try:return json.loads(out.splitlines()[-1])
        except (IndexError,ValueError):return {'status':'failed_process','code':proc.returncode}
    except subprocess.TimeoutExpired:return {'status':'timeout'}
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        if job:ctypes.windll.kernel32.CloseHandle(job)

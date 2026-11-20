import ctypes
from ctypes import wintypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

D = Path(__file__).resolve().parent
def stable(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True)
def sha(s):
    return hashlib.sha256(s if isinstance(s,bytes) else s.encode()).hexdigest()
def read(name):
    p=D/name
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(name,value):
    p=D/name
    p.parent.mkdir(parents=True,exist_ok=True)
    raw=stable(value).encode()
    temp=p.with_suffix(p.suffix+".tmp")
    temp.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)
    os.replace(temp,p)
class Limits(ctypes.Structure):
    _fields_=[("user",ctypes.c_int64),("job",ctypes.c_int64),("flags",wintypes.DWORD),("lo",ctypes.c_size_t),("hi",ctypes.c_size_t),("active",wintypes.DWORD),("aff",ctypes.c_size_t),("priority",wintypes.DWORD),("sched",wintypes.DWORD)]
class Info(ctypes.Structure):
    _fields_=[("limits",Limits),("io",ctypes.c_uint64*6),("process_mem",ctypes.c_size_t),("job_mem",ctypes.c_size_t),("peak_proc",ctypes.c_size_t),("peak_job",ctypes.c_size_t)]
def execute(payload):
    k=ctypes.windll.kernel32
    k.CreateJobObjectW.restype=wintypes.HANDLE
    k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    p=subprocess.Popen([sys.executable,"-I","-B","-S",str(D/"runner.py")],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=D)
    job=k.CreateJobObjectW(None,None)
    try:
        info=Info();info.limits.flags=0x2100;info.process_mem=256*1024*1024
        assert job and k.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) and k.AssignProcessToJobObject(job,int(p._handle))
        out,_=p.communicate(stable(payload).encode(),timeout=9)
        return json.loads(out.splitlines()[-1])
    except (subprocess.TimeoutExpired,IndexError,ValueError) as exc:return {"status":"process","reason":type(exc).__name__}
    finally:
        if p.poll() is None:p.kill();p.wait()
        if job:k.CloseHandle(job)


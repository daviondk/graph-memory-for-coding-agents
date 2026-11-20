"""Windows Job object memory/time bound for one standalone grading process."""
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
from common import ROOT
class Limits(ctypes.Structure):
    _fields_=[('user',ctypes.c_int64),('job',ctypes.c_int64),('flags',wintypes.DWORD),('lo',ctypes.c_size_t),('hi',ctypes.c_size_t),('active',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('sched',wintypes.DWORD)]
class Info(ctypes.Structure):
    _fields_=[('limits',Limits),('io',ctypes.c_uint64*6),('process_mem',ctypes.c_size_t),('job_mem',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
def execute(p,entry,imports,tests):
    d={'source':str(p),'entry':entry,'imports':imports,'tests':tests}
    proc=subprocess.Popen([sys.executable,'-B','-I','-S',str(ROOT/'worker.py')],cwd=p.parent,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    job=None
    try:
        if os.name=='nt':
            k=ctypes.windll.kernel32;k.CreateJobObjectW.restype=wintypes.HANDLE
            k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
            k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];k.CloseHandle.argtypes=[wintypes.HANDLE]
            job=k.CreateJobObjectW(None,None);info=Info();info.limits.flags=0x2100;info.process_mem=192*1024*1024
            assert job and k.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)) and k.AssignProcessToJobObject(job,int(proc._handle))
        try:
            out,_=proc.communicate(json.dumps(d).encode(),timeout=5)
            return json.loads(out.splitlines()[-1])
        except subprocess.TimeoutExpired:return {'status':'timeout'}
        except (ValueError,IndexError):return {'status':'failed_process','code':proc.returncode}
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        if job:k.CloseHandle(job)


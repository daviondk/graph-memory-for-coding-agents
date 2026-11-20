from base import D, Limits, Info, stable
import ctypes,json,sys,subprocess
from ctypes import wintypes

def run_predictions(payload):
    k=ctypes.windll.kernel32
    k.CreateJobObjectW.restype=wintypes.HANDLE
    k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    p=subprocess.Popen([sys.executable,"-I","-B","-S",str(D/"pred_runner.py")],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=D)
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


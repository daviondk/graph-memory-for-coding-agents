"""Supervise a single loopback model in a kill-on-close Windows job."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from resource_watch import Performance

ROOT=Path(__file__).resolve().parent
kernel=ctypes.windll.kernel32

class Limits(ctypes.Structure):
    _fields_=[('user', ctypes.c_int64), ('job_time',ctypes.c_int64), ('flags',wintypes.DWORD),
              ('minws',ctypes.c_size_t), ('maxws',ctypes.c_size_t), ('active',wintypes.DWORD),
              ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]

class JobInfo(ctypes.Structure):
    _fields_=[('basic',Limits),('io',ctypes.c_uint64*6),('process_memory',ctypes.c_size_t),
              ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]

def headroom():
    m=Performance();m.cb=ctypes.sizeof(m)
    assert ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(m),m.cb)
    return m.available*m.page,(m.limit-m.commit)*m.page

def main():
    for port in (18839,18840):
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    ram,commit=headroom()
    if ram<15*1024**3 or commit<25*1024**3:raise RuntimeError('Not enough headroom for the model')
    kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    job=kernel.CreateJobObjectW(None,None)
    assert job
    info=JobInfo();info.basic.flags=0x2000
    assert kernel.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info))
    previous=ROOT/'pre-watchdog'/'service.json'
    if not previous.is_file():previous=ROOT/'service.json'
    args=json.loads(previous.read_text(encoding='utf-8-sig'))['native_arguments']+['--cache-ram','0']
    procs=[]
    def start(command,log_name):
        with (ROOT/log_name).open('ab') as log:
            p=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        procs.append(p)
        if not kernel.AssignProcessToJobObject(job,int(p._handle)):
            raise OSError('Could not assign child to managed job')
        return p
    try:
        model=start([str(ROOT/'bin/llama-server.exe'),*args],'resumed-native.log')
        proxy=start([sys.executable,'-X','utf8',str(ROOT/'seed_proxy.py')],'resumed-proxy.log')
        sample=start([sys.executable,str(ROOT/'resource_watch.py'),str(model.pid),str(ROOT/'resource-resumed.jsonl'),'--interval','5'],'resumed-sample.log')
        (ROOT/'service-resumed.json').write_text(json.dumps(dict(utc_epoch=time.time(),native_pid=model.pid,proxy_pid=proxy.pid,monitor_pid=sample.pid,native_arguments=args,job_kill_on_close=True,one_native_slot=True),indent=2),encoding='utf8')
        pressure=0
        with (ROOT/'guard-resumed.jsonl').open('a',encoding='utf8',buffering=1) as log:
            while all(p.poll() is None for p in procs):
                ram,commit=headroom()
                pressure=pressure+1 if ram<768*1024**2 or commit<5*1024**3 else 0
                stop=pressure>=3 or commit<2*1024**3
                log.write(json.dumps(dict(epoch=time.time(),available=ram,free_commit=commit,pressure_streak=pressure,stop=stop))+'\n')
                if stop:raise RuntimeError('Headroom threshold crossed')
                time.sleep(1)
    finally:
        kernel.CloseHandle(job)
        for p in procs:
            if p.poll() is None:
                p.terminate()

if __name__=='__main__':
    main()

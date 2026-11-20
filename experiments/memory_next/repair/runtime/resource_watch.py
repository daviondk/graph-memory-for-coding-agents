"""Windows system commit, available RAM and exact solver process counters. Writes only to the supplied path."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import time


class Performance(ctypes.Structure):
    _fields_=[("cb",wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in
        ("commit","limit","peak_commit","physical","available","cache","kernel","paged","nonpaged","page")]+[
        (k,wintypes.DWORD) for k in ("handles","processes","threads")]


class Process(ctypes.Structure):
    _fields_=[("cb",wintypes.DWORD),("faults",wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in
        ("peak_working","working","peak_paged","paged","peak_nonpaged","nonpaged","pagefile","peak_pagefile","private")]


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("pid",type=int)
    cli.add_argument("log",type=Path)
    cli.add_argument("--interval",type=float,default=10)
    args=cli.parse_args()
    k=ctypes.windll.kernel32
    p=ctypes.windll.psapi
    k.OpenProcess.restype=wintypes.HANDLE
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    p.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Process),wintypes.DWORD]
    owner=k.OpenProcess(0x101410,False,args.pid)
    if not owner:
        raise OSError("solver process handle could not be opened")
    try:
        while k.WaitForSingleObject(owner,0)==258:
            s=Performance();s.cb=ctypes.sizeof(s)
            m=Process();m.cb=ctypes.sizeof(m)
            if not p.GetPerformanceInfo(ctypes.byref(s),s.cb) or not p.GetProcessMemoryInfo(owner,ctypes.byref(m),m.cb):
                break
            gpu=subprocess.run(["nvidia-smi","--query-gpu=memory.used,memory.free,utilization.gpu","--format=csv,noheader,nounits"],
                               capture_output=True,text=True,timeout=10)
            gl=[float(v.strip()) for v in gpu.stdout.strip().split(",")] if gpu.returncode==0 else [None]*3
            row=dict(epoch=time.time(),pid=args.pid,commit_used_bytes=s.commit*s.page,commit_limit_bytes=s.limit*s.page,
                     commit_free_bytes=(s.limit-s.commit)*s.page,physical_available_bytes=s.available*s.page,
                     rss_bytes=m.working,private_commit_bytes=m.private,peak_process_commit_bytes=m.peak_pagefile,
                     gpu_used_MiB=gl[0],gpu_free_MiB=gl[1],gpu_util_percent=gl[2])
            with args.log.open("a",encoding="utf-8") as f:
                f.write(json.dumps(row)+"\n")
            if k.WaitForSingleObject(owner,int(args.interval*1000))!=258:
                break
    finally:
        k.CloseHandle(owner)


if __name__=="__main__":
    main()

"""Stop only the owned llama-server if Windows runs out of usable headroom."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import time
from resource_watch import Performance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pid',type=int)
    parser.add_argument('log',type=Path)
    args = parser.parse_args()
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE,wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    proc=kernel.OpenProcess(0x101001,False,args.pid)
    if not proc:
        raise OSError('Cannot open owned model worker')
    expected = Path(__file__).resolve().parent/'bin'/'llama-server.exe'
    size=wintypes.DWORD(2048)
    path=ctypes.create_unicode_buffer(size.value)
    assert kernel.QueryFullProcessImageNameW(proc,0,path,ctypes.byref(size))
    assert os.path.samefile(path.value,expected)
    pressure=0
    with args.log.open('a',encoding='utf8',buffering=1) as f:
        while kernel.WaitForSingleObject(proc,1000)==258:
            mem=Performance()
            mem.cb=ctypes.sizeof(mem)
            assert ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(mem),mem.cb)
            free=(mem.limit-mem.commit)*mem.page
            available=mem.available*mem.page
            pressure=pressure+1 if available<768*1024**2 or free<5*1024**3 else 0
            stop=pressure>=3 or free<2*1024**3
            f.write(json.dumps(dict(epoch=time.time(),available=available,free_commit=free,pressure_streak=pressure,stop=stop))+'\n')
            if stop:
                assert kernel.TerminateProcess(proc,75)
                break
    kernel.CloseHandle(proc)


if __name__=='__main__':
    main()

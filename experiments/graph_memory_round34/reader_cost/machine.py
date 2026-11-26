"""Windows OS affinity and resident/private process memory using built-in ctypes."""
import ctypes
from ctypes import wintypes
def process():
    h=ctypes.windll.kernel32.GetCurrentProcess
    h.restype=wintypes.HANDLE
    return wintypes.HANDLE(h())
def pin_one():
    a=ctypes.c_size_t();s=ctypes.c_size_t();h=process();kernel=ctypes.windll.kernel32
    assert kernel.GetProcessAffinityMask(h,ctypes.byref(a),ctypes.byref(s))
    cores=[j for j in range(8*ctypes.sizeof(a)) if a.value&(1<<j)];cpu=cores[len(cores)//2]
    assert kernel.SetProcessAffinityMask(h,ctypes.c_size_t(1<<cpu));return cpu
class Counters(ctypes.Structure):
    _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD),("PeakWorkingSetSize",ctypes.c_size_t),("WorkingSetSize",ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage",ctypes.c_size_t),("QuotaPagedPoolUsage",ctypes.c_size_t),("QuotaPeakNonPagedPoolUsage",ctypes.c_size_t),("QuotaNonPagedPoolUsage",ctypes.c_size_t),
        ("PagefileUsage",ctypes.c_size_t),("PeakPagefileUsage",ctypes.c_size_t),("PrivateUsage",ctypes.c_size_t)]
def memory():
    v=Counters();v.cb=ctypes.sizeof(v);assert ctypes.windll.psapi.GetProcessMemoryInfo(process(),ctypes.byref(v),v.cb)
    return {k:getattr(v,k) for k in ("WorkingSetSize","PeakWorkingSetSize","PrivateUsage")}

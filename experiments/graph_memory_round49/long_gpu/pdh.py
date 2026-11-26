"""Read per-process Windows WDDM cumulative engine execution time via native PDH."""
import ctypes as c,re
from ctypes import wintypes as w
class Filetime(c.Structure):_fields_=[('low',w.DWORD),('high',w.DWORD)]
class Raw(c.Structure):_fields_=[('status',w.DWORD),('timestamp',Filetime),('first',c.c_longlong),('second',c.c_longlong),('count',w.DWORD)]
class Entry(c.Structure):_fields_=[('name',w.LPWSTR),('raw',Raw)]
class Engines:
    def __init__(self):
        self.api=c.WinDLL('pdh.dll');self.q=c.c_void_p();self.handle=c.c_void_p();self.api.PdhOpenQueryW.argtypes=[w.LPCWSTR,c.c_size_t,c.POINTER(c.c_void_p)]
        self.api.PdhAddEnglishCounterW.argtypes=[c.c_void_p,w.LPCWSTR,c.c_size_t,c.POINTER(c.c_void_p)];self.api.PdhCollectQueryData.argtypes=[c.c_void_p]
        self.api.PdhGetRawCounterArrayW.argtypes=[c.c_void_p,c.POINTER(w.DWORD),c.POINTER(w.DWORD),c.c_void_p];self.api.PdhCloseQuery.argtypes=[c.c_void_p]
        self.check(self.api.PdhOpenQueryW(None,0,c.byref(self.q)));self.check(self.api.PdhAddEnglishCounterW(self.q,r'\GPU Engine(*)\Running Time',0,c.byref(self.handle)))
    @staticmethod
    def check(k):
        if k!=0:raise RuntimeError(f'PDH status {k & 0xffffffff:#x}')
    def read(self,pid=None):
        self.check(self.api.PdhCollectQueryData(self.q));size=w.DWORD();n=w.DWORD();self.api.PdhGetRawCounterArrayW(self.handle,c.byref(size),c.byref(n),None)
        if not size.value:return {}
        tmp=c.create_string_buffer(size.value);self.check(self.api.PdhGetRawCounterArrayW(self.handle,c.byref(size),c.byref(n),c.byref(tmp)))
        items=c.cast(tmp,c.POINTER(Entry));out={}
        for i in range(n.value):
            a=items[i];name=a.name or '';m=re.match(r'pid_(\d+)_.*?_eng_(\d+)_engtype_(\w+)',name,re.I)
            if m and (pid is None or int(m[1])==pid) and a.raw.status in (0,1):out[name]=int(a.raw.first)
        return out
    def close(self):self.check(self.api.PdhCloseQuery(self.q))
def delta(before,after):
    result={}
    for k,v in after.items():
        diff=v-before.get(k,0);assert diff>=0
        if diff:result[k.split('_eng_',1)[-1]]=diff/1.e7
    return result
def active(values):return sum(v for k,v in values.items() if re.search(r'3d|compute|cuda',k,re.I))
if __name__=='__main__':
    p=Engines();r=p.read();print('Counters:',len(r),'working:',sum(x>0 for x in r.values()),'max',max(r.values(),default=0));p.close()


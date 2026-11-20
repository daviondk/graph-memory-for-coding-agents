"""Benign fixture edits in an independent process, same-handle metadata and observed range readers."""
import ctypes
import os
import msvcrt
import sys
from ctypes import wintypes
from pathlib import Path
import json

FIELDS = ("mtime","size","dev","ino","change")
class Basic(ctypes.Structure):
    _fields_ = [(x, ctypes.c_longlong) for x in ("creation","access","write","change")] + [("attributes",wintypes.DWORD)]
get_info=ctypes.WinDLL("kernel32",use_last_error=True).GetFileInformationByHandleEx
get_info.argtypes=(wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD)
get_info.restype=wintypes.BOOL
def stamp(path,rich=False):
    if not rich:
        v=os.stat(path)
        return {"mtime":v.st_mtime_ns,"size":v.st_size,"dev":v.st_dev,"ino":v.st_ino}
    with path.open("rb",buffering=0) as f:
        v=os.fstat(f.fileno());out=Basic()
        if not get_info(msvcrt.get_osfhandle(f.fileno()),0,ctypes.byref(out),ctypes.sizeof(out)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"mtime":v.st_mtime_ns,"size":v.st_size,"dev":v.st_dev,"ino":v.st_ino,"change":out.change}
def target(b):
    rows=b.splitlines(keepends=True)
    indexes=sorted(range(4,len(rows)-4),key=lambda i:(abs(i-len(rows)//2),i))
    for i in indexes:
        ln=rows[i][:-1]
        if ln.strip() and len(ln)>6 and ln.isascii():
            return i, (b"# observation"[:len(ln)]+b"."*len(ln))[:len(ln)]+b"\n"
    raise ValueError("no suitable interior line")
def expected(b,case):
    i,repl=target(b);rows=b.splitlines(keepends=True)
    if case.startswith("replace") or case=="atomic_restore":
        rows[i]=repl
        return b"".join(rows)
    if case=="append":return b+b"# external observation\n"
    if case=="prepend":return b"# external observation\n"+b
    return b
def mutate(path,case):
    old=path.read_bytes();new=expected(old,case);s=path.stat()
    if case=="neighbor":path.with_suffix(".notes").write_bytes(b"note outside observed path\n")
    if case=="touch":os.utime(path,ns=(s.st_atime_ns,s.st_mtime_ns+5_000_000_000))
    if case=="atomic_restore":
        temp=path.with_suffix(".tmp");temp.write_bytes(new);os.utime(temp,ns=(s.st_atime_ns,s.st_mtime_ns));os.replace(temp,path)
    if case in ("replace","replace_restore","append","prepend"):
        path.write_bytes(new)
        if case=="replace_restore":os.utime(path,ns=(s.st_atime_ns,s.st_mtime_ns))
    assert path.read_bytes()==new
if __name__=="__main__":mutate(Path(sys.argv[1]),sys.argv[2])

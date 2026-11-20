"""Dedicated sequential external writer. No mutation outside its private root."""
import json,os,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
for message in sys.stdin:
    name,op,data=json.loads(message)
    p=(root/name).resolve()
    assert p.parent == root
    old=p.stat()
    if op=="touch":os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns+5_000_000_000))
    elif op=="neighbor":p.with_suffix(".notes").write_bytes(b"ordinary note")
    elif op=="atomic_restore":
        tmp=p.with_suffix(".tmp");tmp.write_bytes(bytes.fromhex(data));os.utime(tmp,ns=(old.st_atime_ns,old.st_mtime_ns));os.replace(tmp,p)
    elif op not in ("repeat","no_update"):
        p.write_bytes(bytes.fromhex(data))
        if op=="replace_restore":os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns))
    print("ok",flush=True)

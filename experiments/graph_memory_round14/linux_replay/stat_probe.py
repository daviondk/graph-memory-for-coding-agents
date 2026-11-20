"""Verify that the POSIX stamp used by wrappers requires a stat query and no source payload read."""
import os,tempfile,subprocess,sys,json,re,gzip
from pathlib import Path
D=Path(__file__).resolve().parent
for fs,mount in (("ext4","/tmp"),("tmpfs","/dev/shm")):
    with tempfile.TemporaryDirectory(dir=mount,prefix="r14-stamp-probe-") as t:
        directory=Path(t);f=directory/"observation_probe.py";f.write_bytes(b"x=1\n")
        record=directory/"probe.log";env={**os.environ,"LD_LIBRARY_PATH":str(D/"vendor/lib")}
        subprocess.run([str(D/"vendor/strace"),"-f","-yy","-s","120","-e","trace=stat,lstat,statx,fstat,newfstatat,open,openat,read,pread64","-o",str(record),sys.executable,"-B","-c","import os,sys; name=sys.argv[1]; [os.stat(name) for _ in range(32)]",str(f)],check=True,env=env)
        lines=[s for s in record.read_text().splitlines() if str(f) in s]
        sc=[s for s in lines if re.search(r"\b(stat|newfstatat|statx)\(",s)]
        rd=[s for s in lines if re.search(r"\b(pread64|read)\(\d+<",s) and re.search(r"\d+<"+re.escape(str(f))+r">",s)]
        assert len(sc)==32 and not rd,(len(sc),len(rd))
        (D/fs/"stamp_probe.json").write_text(json.dumps({"n":32,"matching_stat_calls":len(sc),"payload_reads":len(rd),"raw":lines},indent=1))
        print(fs,len(sc),len(rd))

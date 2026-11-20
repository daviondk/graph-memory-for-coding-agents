from pathlib import Path
import zipfile, hashlib
d=Path(__file__).resolve().parent
t=d.parent/'agent_memory_trials';out=d.parents[1]/'outputs'
files=sorted(p for p in t.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pyo'} and p.name!='MANIFEST.sha256')
manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(t).as_posix()+'\n' for p in files)
zpath=out/'agent-memory-experiment-records.zip'
with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for p in files:z.write(p,p.relative_to(t).as_posix())
    z.writestr('MANIFEST.sha256',manifest)
print(len(files),zpath.stat().st_size,hashlib.sha256(zpath.read_bytes()).hexdigest())


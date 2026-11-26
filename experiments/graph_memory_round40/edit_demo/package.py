"""Create a reproducible release using the declared portable inputs only."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile
D=Path(__file__).resolve().parent
NAMES=('PLAN_RU.md','REPORT_RU.md','REPRODUCE_RU.md','app.py','index.html','reader.sqlite','witness.sqlite','source-bindings.json','choose.py','build.py','verify.py','browser_check.py','browser-results.json','visitor.png','package.py')

def pack(target):
    entries={name:(D/name).read_bytes() for name in NAMES}
    manifest=(json.dumps({'files':{name:sha256(data).hexdigest() for name,data in entries.items()}},indent=2,sort_keys=True)+'\n').encode()
    if (D/'manifest.json').exists():assert (D/'manifest.json').read_bytes()==manifest
    else:(D/'manifest.json').open('xb').write(manifest)
    entries['manifest.json']=manifest
    with zipfile.ZipFile(target,'x') as z:
        for n,v in sorted(entries.items()):
            info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16
            z.writestr(info,v,compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(target) as z:assert set(z.namelist())==set(entries) and all(z.read(n)==v for n,v in entries.items())
    print('archive',target.stat().st_size,sha256(target.read_bytes()).hexdigest(),'manifest',sha256(manifest).hexdigest(),len(NAMES))
if __name__=='__main__':pack(Path(sys.argv[1]) if len(sys.argv)>1 else D/'code-edit-demo.zip')

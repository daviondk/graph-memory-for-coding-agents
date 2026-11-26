"""Create a content-addressed standalone demo ZIP from the signed manifest."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from tempfile import TemporaryDirectory
from verify import D,verify

FILES=('DATA_SOURCE.md','PROTOCOL_RU.md','REPORT_RU.md','REPRODUCE_RU.md','build.py','demo.png','grader.sqlite','index.html','measure.py','observations.json.gz','package.py','panel.json','provenance.json','reader.py','reader.sqlite','reference.json','results.json','serve.py','smoke.py','ui-check.json','verify.py')
def digest(b):return hashlib.sha256(b).hexdigest()
if __name__=='__main__':
    manifest={n:digest((D/n).read_bytes()) for n in FILES};expected=(json.dumps({'files':manifest},sort_keys=True,indent=2)+'\n').encode()
    f=D/'manifest.json'
    if f.exists():assert f.read_bytes()==expected
    else:
        with f.open('xb') as stream:stream.write(expected)
    verify();output=Path(sys.argv[1]) if len(sys.argv)>1 else D/'isetrace-provenance-demo.zip'
    with zipfile.ZipFile(output,'x') as z:
        for name in sorted((*FILES,'manifest.json')):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16
            z.writestr(info,(D/name).read_bytes(),compress_type=zipfile.ZIP_STORED if name.endswith(('.gz','.png')) else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output) as z:
        assert set(z.namelist())==set(FILES)|{'manifest.json'} and z.read('manifest.json')==expected
        assert all(digest(z.read(n))==sha for n,sha in manifest.items())
    print(digest(output.read_bytes()),output,output.stat().st_size,digest(expected),len(FILES))

"""Build and inspect a deterministic R43 ZIP without executing its contents."""
import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile
from verify import OUTER,ROOT,expected,digest,require,valid_name,verify

def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode()

def inspect(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();require(len(names)==len(set(names)) and all(valid_name(x) for x in names),'duplicate or invalid member')
        require(sum(i.file_size for i in z.infolist())<512*1024**2,'excessive expanded size')
        require(OUTER in names,'missing hash list')
        files=json.loads(z.read(OUTER));require(set(names)==set(files)|{OUTER},'unlisted archive file')
        release=json.loads(z.read('release.json'));require(files==expected(release,z.read),'nested membership or checksums')
        return files

def build(path):
    path=path.resolve();require(not path.exists() and not path.is_relative_to(ROOT),'choose an unused path outside the research tree')
    files=verify();path.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as t:
        tmp=Path(t)/'staged.zip'
        with zipfile.ZipFile(tmp,'x') as z:
            for name in sorted(set(files)|{OUTER}):
                raw=encoded(files) if name==OUTER else (ROOT/name).read_bytes()
                info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16
                z.writestr(info,raw,compress_type=zipfile.ZIP_STORED if name.endswith(('.gz','.mp4','.png','.zip','.pdf')) else zipfile.ZIP_DEFLATED)
        require(inspect(tmp)==verify(),'sources changed during build')
        os.link(tmp,path)
    return files
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('--verify',action='store_true');args=p.parse_args()
    files=inspect(args.zip) if args.verify else build(args.zip)
    print(len(files),digest(args.zip.read_bytes()),args.zip)

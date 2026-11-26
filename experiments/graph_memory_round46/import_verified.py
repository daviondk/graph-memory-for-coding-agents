"""Import a pinned R46 ZIP into a new target only, leaving existing research untouched."""
import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile
from package_verified import inspect
from verify import OUTER,digest,require,verify

def import_to(path,target,sha):
    source=path.resolve();target=target.resolve()
    require(digest(source.read_bytes())==sha,'ZIP SHA-256 mismatch')
    files=inspect(source);require(not target.exists() and target.parent.is_dir(),'target must be new and under an existing directory')
    with TemporaryDirectory(dir=target.parent) as scratch:
        root=Path(scratch)/'stage';root.mkdir()
        with zipfile.ZipFile(source) as z:
            for name in [*files,OUTER]:
                f=root/name;f.parent.mkdir(exist_ok=True,parents=True);f.write_bytes(z.read(name))
        require(verify(root)==files,'staged integrity check failed');os.rename(root,target)
    return len(files)+1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('target',type=Path);p.add_argument('--sha256',required=True);args=p.parse_args()
    print('Imported',import_to(args.zip,args.target,args.sha256),'verified members into',args.target)

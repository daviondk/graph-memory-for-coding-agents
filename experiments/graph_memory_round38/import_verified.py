"""Import only the verified ZIP members into a new directory, atomically."""
import argparse
import os
from pathlib import Path
import tempfile
import zipfile
from package_verified import MANIFEST, inspect
from verify import digest, require, verify

if __name__ == "__main__":
    cli = argparse.ArgumentParser(); cli.add_argument("zip",type=Path); cli.add_argument("target",type=Path); cli.add_argument("--sha256",required=True);args=cli.parse_args()
    source, target = args.zip.resolve(), args.target.resolve()
    require(digest(source.read_bytes()) == args.sha256, "ZIP SHA-256 mismatch")
    files = inspect(source)
    require(not target.exists() and target.parent.is_dir(), "select an unused target under an existing directory")
    with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
        stage = Path(scratch)/"release"; stage.mkdir()
        with zipfile.ZipFile(source) as z:
            for name in [*files,MANIFEST]:
                p=stage/name; p.parent.mkdir(exist_ok=True,parents=True)
                p.write_bytes(z.read(name))
        require(verify(stage) == files,"extracted files differ")
        os.rename(stage,target)
    print(f"Imported {len(files)+1} verified members into {target}")

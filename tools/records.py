"""List evidence, obtain a release asset through gh, or verify downloaded files (Python 3.8+)."""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "catalog" / "release-assets.json").read_text(encoding="utf-8"))
ASSETS = {
    row["name"]: row
    for collection in ("archives", "supplementary", "reports")
    for row in CATALOG[collection]
    if row["location"] == "release"
}

def verify(path, expected, check_zip=False):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if path.stat().st_size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise ValueError("Size or SHA-256 differs: " + path.name)
    if check_zip and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            member = archive.testzip()
            if member is not None:
                raise ValueError("CRC differs: " + path.name + " / " + member)
    print("OK", path.name)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "get", "verify"))
    parser.add_argument("assets", nargs="*")
    parser.add_argument("--directory", type=Path, default=Path("downloads"))
    parser.add_argument("--repo", help="GitHub OWNER/REPOSITORY for gh; defaults to current clone")
    parser.add_argument("--crc", action="store_true", help="Also decompress members to check CRC")
    args = parser.parse_args()
    if args.command == "list":
        for name, row in ASSETS.items():
            print(f"{row['bytes']:>11}  {name}")
        return
    selected = args.assets or sorted(ASSETS)
    unknown = set(selected) - ASSETS.keys()
    if unknown:
        parser.error("Unknown asset(s): " + ", ".join(sorted(unknown)))
    for name in selected:
        dest = args.directory / name
        if args.command == "get" and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["gh", "release", "download", CATALOG["release_tag"], "--pattern", name, "--dir", str(dest.parent)]
            if args.repo:
                cmd += ["--repo", args.repo]
            subprocess.run(cmd, check=True)
        verify(dest, ASSETS[name], check_zip=args.crc)

if __name__ == "__main__":
    main()


"""Pin a separate panel of public commits and fetch only the trees needed for path diffs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from extract import extract, read_json, write_json

PROJECTS = ("python-attrs/attrs", "pytest-dev/pytest", "pypa/pip", "pallets/flask", "encode/httpx",
            "python-jsonschema/jsonschema")

def pin(name):
    remote = "https://github.com/" + name + ".git"
    result = subprocess.check_output(["git", "-c", "credential.helper=", "ls-remote", remote, "HEAD"], timeout=45)
    h, ref = result.strip().split()
    assert len(h) == 40 and ref == b"HEAD"
    return name, h.decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    pinfile = HERE / "pins.json"
    with ThreadPoolExecutor(max_workers=2) as pool:
        if not pinfile.exists():
            assert not args.verify
            frozen = {"protocol_sha256": hashlib.sha256((HERE/"PROTOCOL_RU.md").read_bytes()).hexdigest(),
                      "heads": dict(pool.map(pin, PROJECTS))}
            write_json(pinfile, frozen, False)
        frozen = read_json(pinfile)
        assert set(PROJECTS) == set(frozen["heads"])
        assert frozen["protocol_sha256"] == hashlib.sha256((HERE/"PROTOCOL_RU.md").read_bytes()).hexdigest()
        tasks = [pool.submit(extract, p, rev, args.scratch, False) for p, rev in frozen["heads"].items()]
        streams = dict(t.result() for t in tasks)
    write_json(HERE/"commits.json.gz", streams, args.verify)

if __name__ == "__main__":
    main()

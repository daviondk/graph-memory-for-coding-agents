"""Fetch official pure-Python wheels and record PyPI SHA-256 and release notes. No installation."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
# In each row: source pre-change/post-change, then two distinct target artifacts.
PACKAGES = {
    "packaging": ("20.9","22.0","21.3","23.0"),
    "PyJWT": ("1.7.0","2.0.0","1.7.1","2.0.1"),
    "more-itertools": ("8.4.0","8.6.0","8.5.0","8.7.0"),
}
NOTES = {
    "packaging": "https://github.com/pypa/packaging/blob/22.0/CHANGELOG.rst",
    "PyJWT": "https://pyjwt.readthedocs.io/en/2.0.1/changelog.html#require-explicit-algorithms-in-jwt-decode-by-default",
    "more-itertools": "https://more-itertools.readthedocs.io/en/v8.14.0/versions.html",
}


def fetch(spec):
    package,version = spec
    metadata_url = f"https://pypi.org/pypi/{package}/{version}/json"
    with urllib.request.urlopen(metadata_url,timeout=30) as response:
        metadata = json.load(response)
    wheels = [r for r in metadata["urls"] if r["filename"].endswith("none-any.whl") and r["packagetype"]=="bdist_wheel"]
    assert len(wheels)==1, (package,version,wheels)
    wheel = wheels[0]
    target = ROOT/"wheels"/wheel["filename"]
    if not target.exists():
        with urllib.request.urlopen(wheel["url"], timeout=30) as f:
            payload = f.read()
        assert hashlib.sha256(payload).hexdigest()==wheel["digests"]["sha256"]
        target.write_bytes(payload)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==wheel["digests"]["sha256"]
    return {"project":package,"version":version,"filename":target.name,"metadata_url":metadata_url,"url":wheel["url"],
            "sha256":wheel["digests"]["sha256"],"bytes":target.stat().st_size,"uploaded_utc":wheel["upload_time_iso_8601"],
            "release_notes":NOTES[package],"retrieved_utc":dt.datetime.now(dt.timezone.utc).isoformat()}


if __name__ == "__main__":
    (ROOT/"wheels").mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        results = list(pool.map(fetch, [(p,v) for p,versions in PACKAGES.items() for v in versions]))
    lock = ROOT/"wheels.lock.json"
    if not lock.exists():
        lock.write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
    else:
        old = json.loads(lock.read_text("utf-8"))
        for a,b in zip(old,results,strict=True):
            assert (a["filename"],a["sha256"]) == (b["filename"],b["sha256"])

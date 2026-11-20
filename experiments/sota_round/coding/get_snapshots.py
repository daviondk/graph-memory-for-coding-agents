"""Fetch the exact SWE-bench Verified base commits; materialize evaluator-readable source."""
import hashlib
import json
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
from cache_paths import CACHE

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".json", ".rst"}


def fetch(task):
    iid = task["instance_id"]
    parent = CACHE / "snapshots" / iid
    exists = parent.exists() and any(parent.iterdir())
    parent.mkdir(exist_ok=True, parents=True)
    stamp = ROOT / "receipts" / (iid + ".json")
    stamp.parent.mkdir(exist_ok=True)
    if stamp.exists() and exists:
        old = json.loads(stamp.read_text())
        if old.get("skipped_eligible_symlinks") == 0:
            old["materialized_symlinks"] = old.pop("skipped_eligible_symlinks")
            stamp.write_text(json.dumps(old, indent=2))
        if "materialized_symlinks" in old:
            return
    url = "https://codeload.github.com/" + task["repo"] + "/tar.gz/" + task["base_commit"]
    archive = CACHE / "archives" / (iid + ".tar.gz")
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        with urlopen(Request(url, headers={"User-Agent": "SWE-Explore-run"}), timeout=150) as response:
            data = response.read()
        tmp = archive.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(archive)
    files = 0
    links = []
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts[1:]
            if not parts or PurePosixPath(parts[-1]).suffix.lower() not in EXTENSIONS:
                continue
            target = parent.joinpath(*parts).resolve()
            if not target.is_relative_to(parent.resolve()):
                raise ValueError("archive path escapes snapshot")
            if member.issym():
                links.append((target, (target.parent / member.linkname).resolve()))
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.extractfile(member).read())
            files += 1
    for target, source in links:
        if not source.is_relative_to(parent.resolve()) or not source.is_file():
            raise ValueError("unresolved symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    receipt = {"instance_id": iid, "repo": task["repo"], "base_commit": task["base_commit"], "url": url,
               "archive_bytes": archive.stat().st_size, "sha256": hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(),
               "files": files, "materialized_symlinks": len(links)}
    stamp.write_text(json.dumps(receipt, indent=2))
    print(iid, files, "eligible files", flush=True)


if __name__ == "__main__":
    tasks = json.loads((ROOT / "tasks.json").read_text(encoding="utf8"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, tasks))

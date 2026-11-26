"""Validate R39 evidence bytes, listed outcomes, Markdown targets, and Git blobs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
TOP = ("REPORT_RU.md", "RELATED_WORK_RU.md", "release.json", "verify.py", "package_verified.py", "import_verified.py")
STUDIES = tuple(json.loads((ROOT/"release.json").read_bytes())["completed"])

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

def valid_name(name):
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and p.as_posix() == name and not any(x in {".", "..", ".git"} for x in p.parts) and ":" not in name and "\\" not in name

def inventory(root):
    inventory = {name: digest((root/name).read_bytes()) for name in TOP}
    release = read(root/"release.json")
    require(tuple(release["completed"]) == STUDIES and set(release["manifests"]) == set(STUDIES), "incomplete study register")
    for study in STUDIES:
        path = root/study/"manifest.json"
        signed = read(path)
        entries = signed.get("files", signed)
        require("REPORT_RU.md" in entries, f"missing {study} report")
        require(digest(path.read_bytes()) == release["manifests"][study], f"bad manifest for {study}")
        inventory[study+"/manifest.json"] = release["manifests"][study]
        for name, record in entries.items():
            require(valid_name(name) and name != "manifest.json", f"unsafe path {name}")
            target = root/study/name
            require(target.resolve().is_relative_to((root/study).resolve()), f"out-of-tree path {name}")
            expected = record if isinstance(record,str) else record["sha256"]
            if isinstance(record,dict) and "bytes" in record:
                require(target.stat().st_size == record["bytes"], name)
            require(digest(target.read_bytes()) == expected, f"content mismatch {study}/{name}")
            inventory[study+"/"+name] = expected
    return dict(sorted(inventory.items()))

def links(root, files):
    external = set()
    for name in files:
        if not name.endswith(".md"): continue
        doc = root/name
        for address in re.findall(r"\]\(([^()\s]+)\)", doc.read_text(encoding="utf8")):
            url = urlsplit(address)
            if url.scheme in {"https", "http", "mailto"} or not url.path: continue
            target = (doc.parent/unquote(url.path)).resolve()
            if target.is_relative_to(root):
                require(target.relative_to(root).as_posix() in files, f"unbundled link {name} {address}")
            else:
                require(target.is_relative_to(root.parent), f"external local path {name} {address}")
                key = target.relative_to(root.parent).as_posix()
                require(re.fullmatch(r"graph_memory_round[1-9][0-9]?/.*",key), key)
                external.add(key)
    require(sorted(external) == read(root/"release.json")["prior_series_links"], "unregistered relative links to previous rounds")
    return external

def verify(root=ROOT):
    root = root.resolve()
    files = inventory(root)
    links(root,files)
    release = read(root/"release.json")
    for observation in release["outcome_checks"]:
        value = read(root/observation["file"])
        for component in observation["path"]:
            value = value[component]
        require(value == observation["equals"], f"wrong outcome {observation}")
    outer = root/"MANIFEST_SHA256.json"
    if outer.exists(): require(read(outer) == files, "outer manifest mismatch")
    return files

def verify_git(root, ref, files):
    git = lambda *cmd: subprocess.check_output(["git", "-C", str(root), *cmd])
    repo = Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve()
    prefix = root.resolve().relative_to(repo).as_posix()
    tracked = set(git("ls-tree", "-r", "--name-only", "-z", ref, "--", ".").decode().strip("\x00").split("\x00"))
    names = set(files)|{"MANIFEST_SHA256.json"}
    require(tracked == names, f"unexpected/missing Git files {tracked ^ names}")
    for name in sorted(names):
        require(digest(git("cat-file", "blob", f"{ref}:{prefix}/{name}")) == digest((root/name).read_bytes()), f"Git blob mismatch {name}")
    for prior in read(root/"release.json")["prior_series_links"]:
        git("cat-file", "-e", f"{ref}:{PurePosixPath(prefix).parent/prior}")
    return len(names)

if __name__ == "__main__":
    cli = argparse.ArgumentParser(); cli.add_argument("--git-ref"); args = cli.parse_args()
    files = verify()
    if args.git_ref: print("Verified Git blobs", verify_git(ROOT,args.git_ref,files))
    print("Verified studies", len(STUDIES), "and source files", len(files))

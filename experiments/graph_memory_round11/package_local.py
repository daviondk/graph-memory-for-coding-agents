"""Build, verify or export a byte-for-byte local R11 snapshot, without invoking Git."""
import argparse
import base64
import gzip
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
DEFAULT = Path("D:/CodexResearch/x20-bench-workspace/outputs/graph-memory-round11-records.zip")
MANIFEST = "MANIFEST.sha256"
SERIES = {"readback", "native_dedup", "negative_actions", "multiset_quix"}
# Measurements under multiset_quix/states are portable evidence, as are every model call and trace.
SKIP_DIRS = {"checkout", "checkouts", "worktree", "worktrees", "staging", "stage", "scratch",
             "tmp", "temp", "mirror", "mirrors", "repo", "repos", "models", "model", "weights",
             "cache", "__pycache__", "node_modules", "venv", "env", "dist", "build"}
TEXT = {".py", ".ps1", ".sh", ".md", ".rst", ".json", ".jsonl", ".csv", ".tsv", ".xml",
        ".txt", ".log", ".patch", ".diff", ".yaml", ".yml", ".toml", ".sha256"}
WEIGHTS = {".gguf", ".safetensors", ".pt", ".pth", ".onnx", ".ckpt", ".ggml", ".h5"}
CACHE_SUFFIX = {".pyc", ".pyo", ".tmp", ".part", ".lockfile", ".stdout", ".stderr"}
BAD_WIN = {"con", "aux", "nul", "prn", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 1024)


def canonical(name):
    p = PurePosixPath(name)
    return bool(name and p.as_posix() == name and not p.is_absolute()
                and not re.search(r'[\\:<>"|?*]', name)
                and all(not any(ord(c) < 32 for c in part) and part not in {".", ".."}
                        and not part.endswith((" ", ".")) and part.split(".")[0].casefold() not in BAD_WIN
                        for part in p.parts))


def excluded_dir(name):
    return name.startswith(".") or name.casefold() in SKIP_DIRS or name.casefold().endswith(".git")


OMITTED = {
    ("native_dedup", "vendor"): "Public sqz binaries and upstream source tree, pinned in native_dedup/upstream.json.",
    ("native_dedup", "scratch"): "Disposable execution directories; the per-call receipts are at the study root.",
    ("negative_actions", "git"): "Git mirrors and object caches, reproducible from commit IDs in git_pairs.json.",
}


def output_directory_allowed(parts):
    return (not parts or parts[0] in SERIES) and not any(excluded_dir(s) for s in parts) and parts[:2] not in OMITTED


def file_policy(name, size):
    p = PurePosixPath(name)
    if not output_directory_allowed(p.parts[:-1]):
        return "exclude"
    leaf = p.name.casefold()
    if leaf.startswith(".") or leaf in {"thumbs.db", "desktop.ini", MANIFEST.casefold()}:
        return "exclude"
    ext = p.suffix.casefold()
    # The two local inference logs are small and accompany the raw request/response records.
    if p.parent.parts in {("readback","probe"),("readback","probe","intervention")} and leaf in {"server.stdout","server.stderr"}:
        return "include" if size <= 8*1024**2 else "unknown"
    if ext in WEIGHTS | CACHE_SUFFIX or leaf in {"pytorch_model.bin", "tf_model.h5"}:
        return "exclude"
    if ext in TEXT or (len(p.parts)>1 and ext==".gz"):
        return "include"
    return "unknown"


def inventory():
    result = {}
    unknown = []
    for base, dirs, names in os.walk(ROOT):
        here = Path(base)
        dirs[:] = sorted(d for d in dirs if not linked(here/d)
                         and output_directory_allowed((here/d).relative_to(ROOT).parts))
        for name in names:
            path = here/name
            if linked(path) or not path.is_file():
                continue
            key = path.relative_to(ROOT).as_posix()
            policy = file_policy(key, path.stat().st_size)
            if policy == "exclude":
                continue
            if policy == "unknown":
                unknown.append(key)
                continue
            if not canonical(key):
                raise ValueError(f"Non-portable record name: {key}")
            result[key] = path
    if unknown:
        raise ValueError("Unclassified source extensions; review these records before the final snapshot:\n" + "\n".join(unknown[:50]))
    missing = SERIES - {PurePosixPath(k).parts[0] for k in result}
    if missing:
        raise ValueError("Missing R11 study directories: " + ", ".join(sorted(missing)))
    if len(result) != len({n.casefold() for n in result}):
        raise ValueError("Case-insensitive name collision")
    return dict(sorted(result.items()))


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def hash_files(paths):
    result = {}
    for name,path in paths.items():
        with path.open("rb") as fp:
            result[name] = digest(fp)
    return result


def manifest_bytes(hashes):
    return "".join(f"{v}  {k}\n" for k,v in sorted(hashes.items())).encode("utf-8")


def verify(archive):
    with zipfile.ZipFile(archive) as zip_:
        entries = zip_.infolist()
        names = [e.filename for e in entries]
        if names.count(MANIFEST) != 1 or len(names) != len({n.casefold() for n in names}):
            raise ValueError("Missing manifest or duplicate ZIP path")
        for e in entries:
            if not canonical(e.filename) or not stat.S_ISREG(e.external_attr >> 16):
                raise ValueError(f"Invalid ZIP member: {e.filename}")
            if e.filename != MANIFEST and file_policy(e.filename,e.file_size) != "include":
                raise ValueError(f"Unexpected ZIP member: {e.filename}")
        raw = zip_.read(MANIFEST)
        expected = {}
        for line in raw.decode("utf-8").splitlines():
            m = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if not m or m[2] in expected:
                raise ValueError("Malformed SHA-256 manifest")
            expected[m[2]] = m[1]
        if raw != manifest_bytes(expected) or set(expected) != set(names)-{MANIFEST}:
            raise ValueError("Manifest coverage, ordering or byte format mismatch")
        if SERIES - {PurePosixPath(k).parts[0] for k in expected}:
            raise ValueError("Incomplete study set in archive")
        for name,sha in expected.items():
            with zip_.open(name) as fp:
                if digest(fp) != sha:
                    raise ValueError(f"SHA-256 mismatch: {name}")
        return expected


def write_member(z,name,source):
    entry = zipfile.ZipInfo(name,(1980,1,1,0,0,0))
    entry.create_system = 3
    entry.external_attr = (stat.S_IFREG | 0o644) << 16
    entry.compress_type = zipfile.ZIP_STORED
    with z.open(entry,"w") as out:
        if isinstance(source,bytes):
            out.write(source)
        else:
            shutil.copyfileobj(source,out,1024**2)


def outside(path):
    if path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Output or export must be outside the input tree")


def build(target,replace=False):
    outside(target)
    if target.exists() and not replace:
        raise FileExistsError(target)
    paths = inventory()
    if any(k.endswith("answers_pending") for k in audit_evidence(paths)):
        raise ValueError("Wait for model answers before building the final archive")
    hashes = hash_files(paths)
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name = tempfile.mkstemp(prefix=".round11-records-",suffix=".zip",dir=target.parent)
    os.close(fd)
    stage = Path(name)
    try:
        with zipfile.ZipFile(stage,"w") as zip_:
            for key,path in paths.items():
                with path.open("rb") as fp:
                    write_member(zip_,key,fp)
            write_member(zip_,MANIFEST,manifest_bytes(hashes))
        if verify(stage) != hashes or hash_files(inventory()) != hashes:
            raise RuntimeError("Source changed during packaging; retry when writes finish")
        if replace:
            os.replace(stage,target)
        else:
            os.link(stage,target)
    finally:
        stage.unlink(missing_ok=True)
    return hashes


def export(archive,target):
    outside(target)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Export requires a new directory: {target}")
    hashes = verify(archive)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".round11-export-",dir=target.parent) as tmp:
        staging = Path(tmp)/"records"
        staging.mkdir()
        with zipfile.ZipFile(archive) as zip_:
            for key in [*hashes,MANIFEST]:
                out = staging/key
                out.parent.mkdir(parents=True,exist_ok=True)
                with zip_.open(key) as inp,out.open("xb") as fp:
                    shutil.copyfileobj(inp,fp,1024**2)
        if hash_files({n:staging/n for n in hashes}) != hashes or (staging/MANIFEST).read_bytes() != manifest_bytes(hashes):
            raise RuntimeError("Export differs from verified archive")
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)
        staging.rename(target)


def audit_lock_inputs(files):
    """Summarize resolvable local path/SHA pairs in experiment lock files."""
    counts = Counter()
    omitted = []
    mismatches = []
    cached = {}

    def walk_data(obj,owner,parents=()):
        if isinstance(obj,list):
            for item in obj:
                walk_data(item,owner,parents)
        elif isinstance(obj,dict):
            for key,value in obj.items():
                if isinstance(value,(list,dict)):
                    walk_data(value,owner,parents+(key,))
                    continue
                if not isinstance(value,str) or not re.fullmatch("[a-f0-9]{64}",value):
                    continue
                # Keys such as "source_sha256" are digests, not filesystem paths.
                if "." not in PurePosixPath(key.replace(chr(92),"/")).name and not any(c in key for c in ("/",chr(92))):
                    continue
                if (parents and parents[0] in {"external", "sources"}) or key.startswith("graph_memory_round"):
                    counts["external_or_upstream"]+=1
                    continue
                candidate=(owner.parent/key.replace(chr(92),"/")).resolve()
                if not candidate.is_relative_to(ROOT.resolve()):
                    counts["external_or_upstream"]+=1
                    continue
                if not candidate.is_file():
                    counts["context_relative_or_missing"]+=1
                    continue
                rel=candidate.relative_to(ROOT.resolve()).as_posix()
                if rel not in files:
                    omitted.append((owner.relative_to(ROOT).as_posix(),rel))
                    continue
                if rel not in cached:
                    with files[rel].open("rb") as fp:
                        cached[rel]=digest(fp)
                counts["included_local_sha_pairs"]+=1
                if cached[rel]!=value:
                    mismatches.append((owner.relative_to(ROOT).as_posix(),rel))

    for key,path in files.items():
        if key == "multiset_quix/native_inputs.json":
            # Values are keyed by historical R9 paths inside the accompanying base64 bundle.
            continue
        if path.suffix==".json" and any(token in path.stem.casefold() for token in ("lock","seal","inputs","manifest","verification")):
            walk_data(json.loads(path.read_bytes()),path)
    return {"coverage":dict(counts),"omitted_local_references":omitted,"historical_hash_differences":mismatches}


def audit_evidence(files):
    def document(name):
        return json.loads(files[name].read_bytes())

    def require(key):
        if key not in files:
            raise ValueError(f"Required measurement not included: {key}")

    def match(key, expected):
        require(key)
        with files[key].open("rb") as stream:
            if digest(stream) != expected:
                raise ValueError(f"Study manifest mismatch: {key}")

    counts = {}
    quix = "multiset_quix/"
    manifest = document(quix+"MANIFEST_SHA256.json")
    for name, expected in manifest.items():
        match(quix+name, expected)
    if {p for p in files if p.startswith(quix)} != {quix+"MANIFEST_SHA256.json", *(quix+n for n in manifest)}:
        raise ValueError("The multiset_quix selection differs from its study manifest")
    counts["quix_manifest_records"] = len(manifest)
    native_inputs = document(quix+"native_inputs.json")
    with gzip.open(files[quix+"native_source_and_traces.json.gz"], "rt", encoding="utf8") as packed:
        embedded = json.load(packed)
    if embedded.keys() != native_inputs.keys() or any(
            hashlib.sha256(base64.b64decode(value, validate=True)).hexdigest() != native_inputs[key]
            for key,value in embedded.items()):
        raise ValueError("Embedded original QuixBugs traces or programs differ from native_inputs.json")
    counts["quix_embedded_verified"] = len(embedded)

    negative = "negative_actions/"
    receipts = document(negative+"receipts.json")
    for row in receipts:
        match(negative+"observations/"+row["id"]+".json.gz",row["sha"])
    counts["negative_observations_verified"] = len(receipts)
    pairs = document(negative+"git_pairs.json")
    for case in pairs:
        if document(negative+"git_metadata/"+case["iid"]+".json") != case:
            raise ValueError("Per-case Git revision record differs from git_pairs.json")
    counts["per_case_git_receipts"] = len(pairs)

    native = "native_dedup/"
    for key in ("delivery-lock.json", "verification.json", "native-receipts.gz", "scored.gz",
                "upstream.json","long-tasks.gz","mcp-control.json","mcp-proxy-name-mismatch.json"):
        require(native+key)
    for name, expected in document(native+"delivery-lock.json").items():
        match(native+name,expected)
    for name, expected in document(native+"verification.json")["files"].items():
        match(native+name,expected)

    for path in ("readback/probe/", "readback/probe/intervention/"):
        prefix = path+"calls/"
        calls = set(k for k in files if k.startswith(prefix))
        counts[path+"raw_calls_present"] = len(calls)
        if path+"answers.json" in files:
            answers = document(path+"answers.json")
            expected = {prefix+r["key"]+".json.gz" for r in answers}
            if not expected <= calls:
                raise ValueError(f"Raw inference record missing in {path}")
            counts[path+"recorded_answers"] = len(answers)
            counts[path+"unreferenced_raw_calls"] = len(calls-expected)
        else:
            counts[path+"answers_pending"] = True
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--list",action="store_true",help="list selected paths without writing")
    g.add_argument("--audit",action="store_true",help="print source coverage without writing")
    g.add_argument("--verify",type=Path,metavar="ZIP")
    g.add_argument("--output",type=Path,metavar="ZIP")
    p.add_argument("--replace",action="store_true")
    p.add_argument("--export",type=Path,metavar="NEW_DIRECTORY")
    a=p.parse_args()
    if a.list or a.audit:
        if a.export or a.replace:p.error("inventory flags cannot export or replace")
        files=inventory()
        if a.list:
            print("\n".join(files))
        else:
            counts=Counter(PurePosixPath(s).parts[0] if "/" in s else "(root)" for s in files)
            sizes=Counter()
            for s,f in files.items():sizes[PurePosixPath(s).suffix.casefold()]+=f.stat().st_size
            print(json.dumps({"files":len(files),"studies":counts,"bytes_by_extension":sizes,"excluded_subtrees":{"/".join(k):v for k,v in OMITTED.items()},"evidence_audit":audit_evidence(files),"scientific_lock_audit":audit_lock_inputs(files)},indent=2))
        return
    if a.verify and a.replace:p.error("--verify cannot replace")
    target=(a.verify or a.output or DEFAULT).resolve()
    hashes=verify(target) if a.verify else build(target,a.replace)
    if a.export:export(target,a.export.resolve())
    with target.open("rb") as fp:print(f"{len(hashes)} records | ZIP SHA-256 {digest(fp)} | {target}")
if __name__=="__main__":
    main()
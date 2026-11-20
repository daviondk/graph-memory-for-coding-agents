"""Build and verify a deterministic local research snapshot without touching Git."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
DEFAULT = Path("D:/CodexResearch/x20-bench-workspace/outputs/graph-memory-round8-records.zip")
MANIFEST = "MANIFEST.sha256"
SERIES = {"agent", "anchors", "lazy", "retrieval"}
SKIP = {"base", "checkout", "checkouts", "mirror", "mirrors", "repos", "models", "model", "weights",
        "tmp", "cache", "__pycache__", "node_modules", "venv", "dist", "build"}
EXT = {".py", ".ps1", ".md", ".json", ".jsonl", ".csv", ".tsv", ".patch", ".diff", ".sh", ".yaml", ".yml"}
LAZY_PROJECTED = {"observations.gz", "forecasts.gz", "scores.gz", "ablation_rows.gz"}
BAD_WIN = {"con", "aux", "nul", "prn", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def allowed(rel):
    parts = rel.parts
    if any(p.startswith(".") or p.casefold() in SKIP or p.casefold().endswith(".git") for p in parts):
        return False
    if len(parts) > 1 and parts[0] not in SERIES:
        return False
    name = rel.name.lower()
    if name.startswith("server.") or name == MANIFEST.lower():
        return False
    if rel.suffix.lower() in EXT or name.endswith((".json.gz", ".jsonl.gz")):
        return True
    if len(parts) == 2 and parts[0] == "lazy" and name in LAZY_PROJECTED:
        return True
    return parts[0] == "agent" and "grades_v2" in parts and rel.suffix.lower() in {".log", ".xml"}


def linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 1024)


def inventory():
    files = {}
    for folder, dirs, names in os.walk(ROOT):
        here = Path(folder)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.casefold() not in SKIP
                         and not d.casefold().endswith(".git") and not linked(here / d)
                         and (here != ROOT or d in SERIES))
        for name in names:
            p = here / name
            rel = p.relative_to(ROOT)
            if allowed(rel) and not linked(p) and p.is_file():
                files[rel.as_posix()] = p
    if not SERIES.issubset({s.split("/")[0] for s in files}):
        raise ValueError("Missing one or more R8 studies")
    return dict(sorted(files.items()))


def canonical_name(name):
    p = PurePosixPath(name)
    if not name or p.as_posix() != name or p.is_absolute() or "\\" in name or ":" in name:
        return False
    return all(not any(ord(ch) < 32 for ch in part) and part not in {"", ".", ".."}
               and not part.endswith((" ", ".")) and part.split(".")[0].lower() not in BAD_WIN for part in p.parts)


def sha(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def hashed_files(files):
    values = {}
    for name, p in files.items():
        with p.open("rb") as fp:
            values[name] = sha(fp)
    return values


def verify(path):
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        names = [x.filename for x in infos]
        if len(names) != len(set(n.casefold() for n in names)) or names.count(MANIFEST) != 1:
            raise ValueError("Duplicate names or missing manifest")
        for entry in infos:
            n = entry.filename
            if not canonical_name(n) or not stat.S_ISREG(entry.external_attr >> 16):
                raise ValueError(f"Unexpected ZIP member: {n}")
            if n != MANIFEST and not allowed(PurePosixPath(n)):
                raise ValueError(f"Disallowed ZIP member: {n}")
        expected = {}
        for line in z.read(MANIFEST).decode("utf8").splitlines():
            m = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if not m or m[2] in expected:
                raise ValueError("Malformed manifest")
            expected[m[2]] = m[1]
        if sorted(expected) != sorted(n for n in names if n != MANIFEST):
            raise ValueError("Manifest inventory mismatch")
        for name, expected_hash in expected.items():
            with z.open(name) as fp:
                if sha(fp) != expected_hash:
                    raise ValueError(f"SHA-256 mismatch: {name}")
    return expected


def put(z, name, stream):
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_STORED
    with z.open(info, "w") as out:
        if isinstance(stream, bytes):
            out.write(stream)
        else:
            shutil.copyfileobj(stream, out, 1024*1024)


def outside(path):
    if path.resolve().is_relative_to(ROOT):
        raise ValueError("Output must be outside the source tree")


def build(target, replace=False):
    outside(target)
    if target.exists() and not replace:
        raise FileExistsError(f"Archive already exists, specify --replace to refresh it: {target}")
    files = inventory()
    hashes = hashed_files(files)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, stage = tempfile.mkstemp(prefix=".round8-", suffix=".zip", dir=target.parent)
    os.close(fd)
    stage = Path(stage)
    try:
        with zipfile.ZipFile(stage, "w") as z:
            for name, p in files.items():
                with p.open("rb") as fp:
                    put(z, name, fp)
            put(z, MANIFEST, "".join(f"{h}  {n}\n" for n, h in hashes.items()).encode("utf8"))
        if verify(stage) != hashes or hashed_files(inventory()) != hashes:
            raise RuntimeError("Source changed during packaging; retry after the run finishes")
        if replace:
            os.replace(stage, target)
        else:
            os.link(stage, target)  # same volume, atomic creation, never clobber an existing file
    finally:
        stage.unlink(missing_ok=True)
    return hashes


def export(archive, target):
    outside(target)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Export needs a new directory: {target}")
    hashes = verify(archive)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".round8-export-", dir=target.parent) as parent:
        stage = Path(parent) / "data"
        stage.mkdir()
        with zipfile.ZipFile(archive) as z:
            for name in [*hashes, MANIFEST]:
                out = stage / name
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as inp, out.open("xb") as fp:
                    shutil.copyfileobj(inp, fp)
        if hashed_files({n:stage/n for n in hashes}) != hashes:
            raise RuntimeError("Export verification failed")
        if target.exists():
            raise FileExistsError(target)
        stage.rename(target)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    actions = ap.add_mutually_exclusive_group()
    actions.add_argument("--verify", type=Path, metavar="ZIP", help="verify an existing records ZIP")
    actions.add_argument("--list", action="store_true", help="print the selected source files")
    actions.add_argument("--output", type=Path, metavar="ZIP", help="build at this path instead of the default")
    ap.add_argument("--replace", action="store_true", help="refresh an existing output archive")
    ap.add_argument("--export", type=Path, metavar="NEW_DIRECTORY", help="copy verified records to a new directory")
    args = ap.parse_args()
    if args.list:
        if args.export or args.replace:
            ap.error("--list cannot export or replace")
        print("\n".join(inventory()))
        return
    if args.verify and args.replace:
        ap.error("--verify cannot replace")
    target = (args.verify or args.output or DEFAULT).resolve()
    hashes = verify(target) if args.verify else build(target, args.replace)
    if args.export:
        export(target, args.export)
    with target.open("rb") as fp:
        print(f"{len(hashes)} research files; ZIP SHA-256 {sha(fp)}; {target}")


if __name__ == "__main__":
    main()

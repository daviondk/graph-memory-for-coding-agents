"""Collect the prespecified second panel, using the same no-blob Git and independent tree audit."""
import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "replication"))
from collect import load, remote, save, snapshot

PROJECTS = ("pygments/pygments", "python-pillow/Pillow", "pydata/xarray",
            "dask/dask", "pypa/hatch", "astropy/astropy")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-git", action="store_true")
    args = parser.parse_args()
    pins_file = HERE / "heads.json"
    if not pins_file.exists():
        save(pins_file, {name: remote(name) for name in PROJECTS})
    pins = load(pins_file)
    assert set(pins) == set(PROJECTS)
    sources = HERE / "events.json.gz"
    report = HERE / "git-audit.json"
    events = load(sources) if sources.exists() else {}
    audit = load(report) if report.exists() else {}
    for name in PROJECTS:
        if name in events and name in audit and not args.verify_git:
            continue
        with TemporaryDirectory(dir=HERE, prefix="git-objects-") as tmp:
            rows, lock, raw, size = snapshot(name, pins[name], tmp)
        if args.verify_git:
            assert rows == events[name] and lock == audit[name]["pins"] and raw == audit[name]["objects"]
        else:
            events[name] = rows
            audit[name] = {"pins": lock, "objects": raw, "temporary_bytes": size}
            save(sources, events)
            save(report, audit)
        print(name, len(rows), size, flush=True)


if __name__ == "__main__":
    main()

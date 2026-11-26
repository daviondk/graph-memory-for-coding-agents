"""Replay all registered checks in a separate tree with only published inputs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent

def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--out", type=Path)
    cli.add_argument("--scratch", type=Path)
    cli.add_argument("--quiet", action="store_true")
    args = cli.parse_args()
    release = json.loads((ROOT / "release.json").read_bytes())
    receipt = {}
    with tempfile.TemporaryDirectory(dir=args.scratch) as name:
        scratch = Path(name).resolve()
        stage = scratch / "graph_memory_round48"
        cwd = scratch / "unrelated"
        cwd.mkdir()
        for item in release["top_documents"]:
            if item.startswith("portable_inputs/"):
                copy_file(ROOT / item, scratch / item.removeprefix("portable_inputs/"))
            if item.startswith("independent_control/"):
                copy_file(ROOT / item, stage / item)
        for study in release["completed"]:
            manifest = json.loads((ROOT / study / "manifest.json").read_bytes())
            for item in [*manifest.get("files", manifest), "manifest.json"]:
                copy_file(ROOT / study / item, stage / study / item)
        # The exact signed R39 database is already shipped by the new demo.
        shared = scratch / "graph_memory_round39/provenance_packet_demo/reader.sqlite"
        copy_file(stage / "observed_demo/apps/trace/runtime/reader.sqlite", shared)
        env = {k:v for k,v in os.environ.items() if not k.startswith("PYTHON")}
        env.update(TEMP=str(scratch), TMP=str(scratch))
        def run(script, *params):
            cp = subprocess.run([sys.executable, "-E", "-s", "-B", "-X", "utf8", str(script), *params],
                                cwd=cwd, env=env, capture_output=True, timeout=240)
            if cp.returncode:
                raise RuntimeError(str(script) + "\n" + (cp.stdout + cp.stderr).decode("utf8","replace")[-2500:])
            if not args.quiet:
                print(script.parent.name, script.name, "verified", flush=True)
        for study in release["completed"]:
            script = "verify.py"
            run(stage / study / script)
            receipt[study] = {"script":script, "exit":0}
        run(stage / "independent_control" / "check.py", "--export", str(shared))
        for script in ("compare.py",):
            run(stage / "independent_control" / script)
    if args.out:
        raw = (json.dumps(receipt,indent=2,sort_keys=True)+"\n").encode()
        if args.out.is_file():
            assert args.out.read_bytes() == raw
        else:
            args.out.write_bytes(raw)

if __name__ == "__main__":
    main()

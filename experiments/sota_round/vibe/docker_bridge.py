from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    args = sys.argv[1:]
    wsl = ["wsl.exe", "-d", "CodexX20MSR", "--exec", "/usr/bin/docker"]
    if args[:2] != ["run", "-d"]:
        return subprocess.run([*wsl, *args]).returncode
    receipt = Path(os.environ["VIBE_CONTAINER_RECEIPT"])
    # A live scheduler from before the amendment may still have its old plan in memory.
    # Stop that scheduler before allocating a container or making any model call.
    if "pilot_agent" in receipt.parts and receipt.parent.name != "seed0":
        print("Seed outside the amended 8B assignment; preflight stop", file=sys.stderr)
        return 76
    cohort = json.loads(Path(os.environ["VIBE_COHORT"]).read_text(encoding="utf-8"))
    targets = {t["image_name"]: t for t in cohort["targets"]}
    image = args[-3]
    target = targets[image]
    # Mini's -w /testbed creates an empty directory in the original authors' image.
    # Replace only that empty directory in this disposable container.
    proc = subprocess.run([*wsl, "run", "--network=none", *args[1:]], capture_output=True)
    if proc.returncode:
        sys.stderr.buffer.write(proc.stderr)
        return proc.returncode
    cid = proc.stdout.decode("ascii").strip()
    Path(os.environ["VIBE_CONTAINER_RECEIPT"]).write_text(cid, encoding="ascii")
    repo = "/" + target["repo"].split("/")[1]
    init = 'set -eu; test "$(git -C "$1" rev-parse HEAD)" = "$2"; rmdir /testbed; ln -s "$1" /testbed; test "$(git -C /testbed rev-parse HEAD)" = "$2"'
    link = subprocess.run([*wsl, "exec", cid, "sh", "-c", init, "sh", repo, target["base_commit"]])
    if link.returncode:
        subprocess.run([*wsl,"rm","-f",cid], capture_output=True)
        return link.returncode
    print(cid)
    return 0


if __name__ == "__main__":
    sys.exit(main())

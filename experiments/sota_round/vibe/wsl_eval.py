"""Invoke the unmodified official vendor evaluator under WSL so its temporary bind mount is native."""
import os
from pathlib import Path
import subprocess
import sys


def wsl_path(value):
    p=Path(value).resolve()
    return "/mnt/"+p.drive[0].lower()+"/"+"/".join(p.parts[1:])


release=Path(os.environ["VIBE_RELEASE"])
args=sys.argv[1:]
for opt in ["--json","--report-json"]:
    if opt in args:
        index=args.index(opt)+1
        args[index]=wsl_path(args[index])
cmd=["wsl.exe","-d","CodexX20MSR","--cd",wsl_path(Path.cwd()),"--exec","python3",
     wsl_path(release/"scripts"/"vendor"/"eval.py"),*args]
sys.exit(subprocess.run(cmd).returncode)

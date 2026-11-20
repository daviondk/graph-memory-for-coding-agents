"""Run upstream eval under WSL; the Docker bridge limits network/CPU only."""
import os,subprocess,sys
from pathlib import Path
here=Path(__file__).resolve().parent
release=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
def linux(p):
    s=Path(p).resolve().as_posix()
    return "/mnt/"+s[0].lower()+s[2:]
args=sys.argv[1:]
for option in ("--json","--report-json"):
    ix=args.index(option)+1;args[ix]=linux(args[ix])
wd=Path.cwd()
cmd=["wsl.exe","-d","CodexX20MSR","--cd",linux(wd),"--exec","env","PATH="+linux(here/"bin")+":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
     "PYTHONDONTWRITEBYTECODE=1","R12_LAUNCH_LOG="+linux(wd/"container.log"),"python3","-B",linux(release/"scripts/vendor/eval.py"),*args]
sys.exit(subprocess.run(cmd).returncode)

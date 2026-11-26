"""Restore only pinned public Git source mirrors for the solver experiment."""
import os
from study import *
def main():
    RAW.mkdir(parents=True,exist_ok=True)
    for repo,(head,*_) in SPECS.items():
        path=RAW/repo.replace("/","__")
        if not path.exists():
            subprocess.run(["git","init","--bare","--quiet",str(path)],check=True)
        ok=subprocess.run(["git","-C",str(path),"cat-file","-e",head+"^{commit}"],capture_output=True)
        enough=ok.returncode==0 and int(git(repo,"rev-list","--first-parent","--count",head))>=194
        if not enough:
            subprocess.run(["git","-C",str(path),"fetch","--no-tags","--depth=400",
                            "https://github.com/"+repo+".git",head],check=True,
                           env={**os.environ,"GIT_TERMINAL_PROMPT":"0"})
        assert int(git(repo,"rev-list","--first-parent","--count",head))>=194
        print(repo,head)
if __name__=="__main__":main()

"""Read exactly the same prefix and native href resolver as on dev, writing only confirmation outputs."""
import os
from pathlib import Path
import sys
here=Path(__file__).resolve().parent
os.environ["R52_WIKI_WORK"]="D:/CodexResearch/x20-r52-directory-confirm"
sys.path.insert(0,str(here.parent/"global_titles"))
import open_first
class OutputPaths:
    def __truediv__(self,name):
        return (here.parent/'global_titles'/name) if name=='retrieval.cpp' else (here/name)
open_first.ROOT=OutputPaths()
if __name__=="__main__":
    open_first.extract()


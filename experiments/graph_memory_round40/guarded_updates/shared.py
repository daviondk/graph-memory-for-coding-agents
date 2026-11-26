from pathlib import Path
import sys
D=Path(__file__).resolve().parent
W=D.parents[1];VF=D.parent/"view_fidelity";SPAN=D.parent/"span_updates";NAT=D.parent/"natural_invalidations"
sys.path.insert(0,str(VF))
from data import R38,RAW,raw_events,read,save,sha,h


def signed(directory,name):
    p=directory/name
    assert sha(p)==read(directory/"manifest.json")["files"][name]
    return read(p)

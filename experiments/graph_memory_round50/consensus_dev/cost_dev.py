"""Use unchanged individual-budget algorithm and bootstrap on official development records."""
from pathlib import Path
import hashlib,sys
D=Path(__file__).resolve().parent
P=D.parent/"packet_consensus";W=D.parents[1]
sys.path.insert(0,str(P))
import cost_match as c
class Folder:
    def __truediv__(self,name):return P/name if name=="BUDGET_CONTROL_RU.md" else D/name
def main():
    assert c.sha(D/"BUDGET_PROTOCOL_RU.md")=="57915b47493bce01b0e32e60d08d02dc60340c956ebbabd8fdbacd03f220b2a1"
    assert c.sha(P/"cost_match.py")==c.read(P/"manifest.json")["files"]["cost_match.py"]
    c.D=Folder()
    def local(k):
        pk=D/k;assert c.sha(pk)==c.read(D/"input-seal.json")["files"][k];return pk
    c.signed=local;c.forecast()
    g=W/"graph_memory_round34/interval_witness";ap=g/"dev-atoms.json.gz"
    assert c.sha(ap)==c.read(g/"dev-geometry.json")["atoms"]
    rows=c.read(ap)
    ag={hashlib.sha256(q.encode()).hexdigest():[[b-a,ws] for _,a,b,ws in marks] for q,marks in rows.items()}
    def labels(folder,key):
        assert key=="judgments.json.gz";return ag
    c.study_data=labels;c.analysis()
if __name__=="__main__":main()


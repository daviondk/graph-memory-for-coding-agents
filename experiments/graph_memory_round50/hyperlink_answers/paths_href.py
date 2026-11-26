from pathlib import Path
import sys
D=Path(__file__).resolve().parent
W=D.parents[1];R49=W/"graph_memory_round49/qa_transfer"
H=D.parent/"hyperlink_control";P=Path("D:/CodexResearch/x20-r50-hyperlink-answers")
PRIOR={"train":D.parent/"qa_replication","dev":D.parent/"qa_external"}
VISIBLE={"train":Path("D:/CodexResearch/x20-r50-qa-replication"),"dev":Path("D:/CodexResearch/x20-r50-qa-external")}
sys.path.insert(0,str(R49))
from common import get,put,sha,hexb
HANDOFF="8983736ca23bbe18337053578f291b2cd5c687dc2d046db30125f98f1e01cc07"
ARMS=("union","href","true")

def fixed():
    assert sha(H/"handoff.json")==HANDOFF
    h=get(H/"handoff.json")
    for split,rec in h["subsets"].items():assert rec["sha256"]==sha(H/rec["file"])
    return dict(protocol=sha(D/"PROTOCOL_RU.md"),handoff=HANDOFF,
        manifests={s:sha(d/"manifest.json") for s,d in PRIOR.items()},visible_clip=h["clip_seal"],prediction_seal=h["prediction_seal"])
def check():assert fixed()==get(D/"registration.json")
if __name__=="__main__":
    assert not (D/"registration.json").exists()
    put(D/"registration.json",fixed())

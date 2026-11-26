from pathlib import Path
import sys
D=Path(__file__).resolve().parent
W=D.parents[1]
REP=D.parent/"qa_replication"
R49=W/"graph_memory_round49/qa_transfer"
EXT=D.parent/"qa_external"
P=Path("D:/CodexResearch/x20-r50-semantic-address")
OLD=Path("D:/CodexResearch/x20-r50-qa-replication")
DATA=Path("D:/CodexResearch/x20-r50-qa-external")
ENCODER=Path("D:/CodexResearch/x20-r39-embedding-runtime/Qwen3-Embedding-8B-Q4_K_M.gguf")
DIGEST="3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85"
sys.path.insert(0,str(R49))
from common import get,put,sha,hexb,MODEL,SERVER
ARMS=("linked_dense","dense","true","lex")

def registration():
    return dict(protocol=sha(D/"PROTOCOL_RU.md"),panel=sha(REP/"manifest.json"),encoder=DIGEST,
        runtime=sha(SERVER),old_inputs=sha(REP/"input-seal.json"),model=sha(MODEL))

def check():
    a=get(D/"registration.json")
    assert a["protocol"]==sha(D/"PROTOCOL_RU.md") and a["panel"]==sha(REP/"manifest.json") and a["encoder"]==DIGEST

if __name__=="__main__":
    assert not (D/"registration.json").exists() and sha(ENCODER)==DIGEST
    put(D/"registration.json",registration())

from pathlib import Path
import sys
D=Path(__file__).resolve().parent;SEM=D.parent/"semantic_address";REP=D.parent/"qa_replication"
W=D.parents[1];R49=W/"graph_memory_round49/qa_transfer";EXT=D.parent/"qa_external"
P=Path("D:/CodexResearch/x20-r50-adaptive-address");OLD=Path("D:/CodexResearch/x20-r50-qa-replication")
TRAIN=OLD/"train.parquet";DATA=Path("D:/CodexResearch/x20-r50-qa-external")
DEV=Path("D:/CodexResearch/x20-r32-2wiki/dev.parquet");HP=Path("D:/CodexResearch/x20-r31-hotpot/blind.json.gz")
MQ=[Path("D:/CodexResearch/x20-r46-reader-transfer/musique-train.jsonl"),Path("D:/CodexResearch/x20-r32-musique/musique.jsonl")]
ENCODER=Path("D:/CodexResearch/x20-r39-embedding-runtime/Qwen3-Embedding-8B-Q4_K_M.gguf")
DIGEST="3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85"
sys.path.insert(0,str(R49))
from common import get,put,sha,hexb,SERVER,MODEL
ARMS=("adaptive","quarter","linked_dense","dense")
def fixed():
    return dict(protocol=sha(D/"PROTOCOL_RU.md"),semantic=sha(SEM/"manifest.json"),parent=sha(REP/"manifest.json"),
                encoder=DIGEST,runtime=get(SEM/"registration.json")["runtime"])
def check():assert fixed()==get(D/"registration.json")
if __name__=="__main__":
    assert not (D/"registration.json").exists()
    put(D/"registration.json",fixed())

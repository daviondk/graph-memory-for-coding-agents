from pathlib import Path
import sys

D=Path(__file__).resolve().parent
W=D.parents[1]
EXT=D.parent/"qa_external"
R49=W/"graph_memory_round49/qa_transfer"
P=Path("D:/CodexResearch/x20-r50-qa-replication")
DATA=Path("D:/CodexResearch/x20-r50-qa-external")
TRAIN=P/"train.parquet"
DEV=Path("D:/CodexResearch/x20-r32-2wiki/dev.parquet")
HP=Path("D:/CodexResearch/x20-r31-hotpot/blind.json.gz")
MQ=[Path("D:/CodexResearch/x20-r46-reader-transfer/musique-train.jsonl"),Path("D:/CodexResearch/x20-r32-musique/musique.jsonl")]
sys.path.insert(0,str(R49))
from common import get,put,sha,hexb

def registered():
    paths={"protocol":D/"PROTOCOL_RU.md","previous":EXT/"manifest.json","train":TRAIN,"dev":DEV,"hotpot":HP,
           "musique_train":MQ[0],"musique_dev":MQ[1],"official_source":EXT/"official-source.json"}
    return {k:sha(v) for k,v in paths.items()}

def check():
    assert registered()==get(D/"registration.json")

if __name__=="__main__":
    assert not (D/"registration.json").exists()
    put(D/"registration.json",registered())

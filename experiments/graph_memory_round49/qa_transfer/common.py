from pathlib import Path
import sys
D=Path(__file__).resolve().parent
W=D.parents[1]
R46=W/"graph_memory_round46/reader_transfer"; R47=W/"graph_memory_round47/edge_placebo"
sys.path.insert(0,str(R47))
from base47 import get,put,sha,hexb,ARMS,SEEDS,MODEL,SERVER
P=Path("D:/CodexResearch/x20-r49-qa-transfer")
DEV=Path("D:/CodexResearch/x20-r32-musique/musique.jsonl")
TRAIN=Path("D:/CodexResearch/x20-r46-reader-transfer/musique-train.jsonl")
URL="https://drive.usercontent.google.com/download?id=1tGdADlNjWFaHLeZZGShh2IRcpO6Lv24h&export=download&confirm=t"
PORT=18896
def files():
    return {"protocol":D/"PROTOCOL_RU.md","r46":R46/"manifest.json","r47":R47/"manifest.json",
            "dev_mirror":DEV,"train_mirror":TRAIN,"choose":W/"graph_memory_round31/observed_links/predict.py",
            "evidence":W/"graph_memory_round32/observed_transfer/transfer.py",
            "place":R47/"rewire.py","metric":DEV.parent/"author/metrics/answer.py"}
def check():
    r=get(D/"registration.json")
    for k,p in files().items():assert sha(p)==r[k]
    return r
if __name__=="__main__":
    assert not (D/"registration.json").exists()
    put(D/"registration.json",{k:sha(p) for k,p in files().items()})

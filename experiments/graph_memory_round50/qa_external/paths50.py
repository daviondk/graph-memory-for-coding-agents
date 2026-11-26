from pathlib import Path
import sys
D50=Path(__file__).resolve().parent;W50=D50.parents[1]
R49=W50/"graph_memory_round49/qa_transfer"
R32=W50/"graph_memory_round32/observed_transfer"
sys.path.insert(0,str(R49))
from common import ARMS,SEEDS,hexb,get,put,sha
P50=Path("D:/CodexResearch/x20-r50-qa-external")
RAW=Path("D:/CodexResearch/x20-r32-2wiki/dev.parquet")
AUTHOR_COMMIT="13800e5be57df1b4040b9b1588c6c811779e69e9"
OFF_URL="https://dl.dropboxusercontent.com/s/7ep3h8unu2njfxv/data_ids.zip"
def registration():
    return dict(protocol=sha(D50/"PROTOCOL_RU.md"),r49=sha(R49/"manifest.json"),r32=sha(R32/"manifest.json"),raw=sha(RAW),n=960,
                seeds=SEEDS,author_commit=AUTHOR_COMMIT,official_data=OFF_URL)
def check50():
    import json
    assert get(D50/"registration.json")==json.loads(json.dumps(registration()))
if __name__=="__main__":put(D50/"registration.json",registration())

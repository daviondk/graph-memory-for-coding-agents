from pathlib import Path
import sys
D=Path(__file__).resolve().parent
W=D.parents[1]
R46=W/'graph_memory_round46/reader_transfer'
LONG=R46.parent/'reader_length'
P47=Path('D:/CodexResearch/x20-r47-edge-placebo')
sys.path.insert(0,str(R46))
from io46 import get,put,sha,hexb,PRIVATE,MODEL,SERVER
SEEDS=(47011,47023,47039,47051,47063)
ARMS=('true','lex')+tuple('sham'+str(s) for s in SEEDS)
def check():
    r=get(D/'registration.json')
    assert r['protocol']==sha(D/'PROTOCOL_RU.md')
    assert r['base']==sha(R46/'manifest.json') and r['long']==sha(LONG/'manifest.json')
def signed(folder,name):
    p=folder/name;assert sha(p)==get(folder/'manifest.json')['files'][name]
    return get(p)

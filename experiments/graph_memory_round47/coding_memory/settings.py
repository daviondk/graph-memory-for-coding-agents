from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent
P=Path('D:/CodexResearch/x20-r47-click-agents')
B=Path('D:/CodexResearch/x20-r47-click-inputs/repository')
ISSUE=B.parent/'problem.txt'
ISSUE_HASH='f5b752ed841829362e93fad0ddabd2f4deea18f199d46d1a85128e56e173d107'
PORT=18878
UNIT=464
LIMITS={'list':2,'search':8,'read':12,'edit':6,'source_bytes':12000,'files':3}
def h(b):return hashlib.sha256(b).hexdigest()
def sha(p):return h(p.read_bytes())
def load(p):return json.loads(p.read_bytes())
def dump(p,x):
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_bytes((json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode())
    tmp.replace(p)

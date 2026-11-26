from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent
P=Path('D:/CodexResearch/x20-r49-woodwork-actors')
B=P/'repository'
ISSUE=B.parent/'problem.txt'
ISSUE_HASH='f923f548cb17e05e705142d7e07e6a9cc59deb77b1f2444bcaf230b0aafc3955'
PORT=18891
UNIT=464
LIMITS={'list':2,'search':12,'read':18,'edit':8,'source_bytes':16000,'files':3}
def h(b):return hashlib.sha256(b).hexdigest()
def sha(p):return h(p.read_bytes())
def load(p):return json.loads(p.read_bytes())
def dump(p,x):
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_bytes((json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode())
    tmp.replace(p)

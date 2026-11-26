"""Create independent workspaces and the concealed, pre-actor condition assignment once."""
import secrets,shutil
from settings import *
def main():
    if (P/'assignment.json').exists():raise RuntimeError('Already assigned')
    assert sha(ISSUE)==ISSUE_HASH and load(D/'packet-seal.json')['history']==sha(D/'history.json')
    names=['graph','flat','none'];secrets.SystemRandom().shuffle(names);mapping={};addr=[]
    for i,name in enumerate(names):
        token=secrets.token_urlsafe(24);label=f'actor-{i+1}'
        folder=P/label;folder.mkdir(exist_ok=False)
        shutil.copytree(B,folder/'checkout',ignore=shutil.ignore_patterns('.git','__pycache__'))
        (folder/'memory.txt').write_bytes((P/(name+'.txt')).read_bytes())
        dump(folder/'session.json',dict(started=False,counts={},bytes=0,edits={},logs=[],frozen=None))
        mapping[token]=dict(label=label,condition=name)
        addr.append(dict(label=label,endpoint=f'http://127.0.0.1:{PORT}/v1/'+token))
    dump(P/'assignment.json',mapping);dump(P/'launch.json',addr)
    dump(D/'handoff-seal.json',dict(assignment=sha(P/'assignment.json'),packets=sha(D/'packet-seal.json'),
        prompt=sha(D/'ACTOR_PROMPT.txt'),gateway=sha(D/'gateway.py'),setup=sha(D/'setup.py'),
        checkout_commit=load(D/'registration.json')['commit'],issue=ISSUE_HASH,actors=3,port=PORT))
    print('three workspaces sealed')
if __name__=='__main__':main()

"""Collect opaque frozen patches for the independent evaluator; no scoring or test reads."""
from settings import *
def main():
    launch=load(P/'launch.json');state=[]
    assert sha(P/'assignment.json')==load(D/'handoff-seal.json')['assignment']
    for entry in launch:
        label=entry['label'];folder=P/label;current=load(folder/'session.json')
        f=current['frozen']
        if f is None:raise SystemExit('Waiting for all three finish receipts')
        assert sha(folder/'change.patch')==f['patch_sha256']
        state.append(dict(actor=label,patch=str(folder/'change.patch'),receipt=f,log_sha=sha(folder/'session.json')))
    dump(P/'blind-grading-handoff.json',state)
    print('Three frozen patches. Blind grading receipt:',sha(P/'blind-grading-handoff.json'))
if __name__=='__main__':main()

"""Run the original three study arms again in empty workspaces, allowing only archived exact HTTP bodies."""
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

os.environ['PYTHONUTF8']='1'
import experiment as runtime

BASE=Path(__file__).resolve().parent

def offline(*args,**kwargs):
    raise RuntimeError('unexpected HTTP request in offline actor replay')

def main():
    lock=json.loads((BASE/'decision_lock.json').read_bytes())
    assert len(lock)==120
    for name,sha in lock.items():
        assert hashlib.sha256((BASE/'trials'/name).read_bytes()).hexdigest()==sha
    runtime.requests.post=offline
    counts=collections.Counter()
    with tempfile.TemporaryDirectory(prefix='primary-actor-replay-',dir=BASE) as temp:
        dest=Path(temp)
        for folder in ('work','trials','failures'):
            (dest/folder).mkdir()
        shutil.copytree(BASE/'calls',dest/'calls')
        runtime.ROOT=dest
        for name in sorted(lock):
            rec=runtime.read(BASE/'trials'/name)
            runtime.task(rec['id'],rec['arm'])
            again=runtime.read(dest/'trials'/name)
            assert rec==again,(name,[k for k,v in rec.items() if again.get(k)!=v])
            counts['trials']+=1
            counts['requests']+=len(rec['requests'])
            counts['restoration_events']+=rec['race_events']
    result={'offline':True,'equal_all_trial_fields':True,**counts}
    path=BASE/'actor_replay.json'
    if path.exists():assert json.loads(path.read_bytes())==result
    else:path.write_text(json.dumps(result,indent=2),encoding='utf8')
    print('PASS',result)

if __name__=='__main__':main()

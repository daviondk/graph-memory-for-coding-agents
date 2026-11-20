"""Check whether the archived policies reproduce with Python's randomized string hashes."""
import collections
import json
import os
import subprocess
import sys
import ast
from independent_audit import HERE, get, memories, write

SEEDS=(0,1,11,113,2026,9077)
def child():
    saved={p['id']:p['mem'] for p in get('packets.json')}
    mismatches={}
    for v in get('visible.json'):
        now=memories(v)
        for a,memory in now.items():
            if memory!=saved[v['id']][a]:mismatches.setdefault(a,[]).append(v['id'])
    print(json.dumps(mismatches))
def run():
    all_results={}
    for seed in SEEDS:
        out=subprocess.check_output([sys.executable,str(HERE/'independent_stability.py'),'--child'],env={**os.environ,'PYTHONHASHSEED':str(seed)},cwd=HERE)
        all_results[str(seed)]=json.loads(out)
    write('independent_stability.json',{'mismatches_teacher':all_results,'tasks':108,'arms':6})
if __name__=='__main__':
    child() if sys.argv[1:]==['--child'] else run()


"""Immediate, outcome-blind check of per-arm writer state and fallbacks using synthetic replies."""
import ast
from collections import Counter,defaultdict
from itertools import permutations
from unittest.mock import patch

import online
from independent_audit import HERE, digest, write

NAMES=['add','sum_all','multiply','last','reset']
ARMS=['graph','bm25_line','full']


def run():
    toy={'id':'ToyDataFlow','cls':'ToyDataFlow','interfaces':[f'def {n}(self):' for n in NAMES],
         'targets':[(n,f'def {n}(self):\n    """Synthetic method {n}"""') for n in NAMES],
         'summary':'Synthetic class','constructor':'class ToyDataFlow:\n    pass','imports':[]}
    histories=defaultdict(list); calls=[]; captured={}; reach=Counter()
    def reader(row):
        labels=[p['method'] for p in row['previous']]
        assert labels==NAMES[:NAMES.index(row['name'])]
        prior_values='|'.join(p['src'].splitlines()[-1].strip() for p in row['previous'])
        return {a:f'{a} {prior_values}' for a in ARMS}
    def respond(req):
        text=req['messages'][1]['content']
        current=next(n for n in NAMES if text.endswith(f'"""Synthetic method {n}"""'))
        segment=text.split('source order, indentation omitted):\n',1)[1].split('\nImplement the following',1)[0]
        if current==NAMES[0]:
            assert segment=='(empty)'
            arm='initial'; code=f'def {current}(self): return "initial"'
        else:
            arm,values=segment.split(' ',1)
            assert arm in ARMS
            seen=values.split('|')
            expected=['return \'initial\'']+[
                "raise NotImplementedError" if arm=='full' and n=='multiply' else f"return '{arm}_{n}'"
                for n in NAMES[1:NAMES.index(current)]]
            assert seen==expected
            code='not a function' if arm=='full' and current=='multiply' else f'def {current}(self): return "{arm}_{current}"'
        calls.append((arm,current));key=digest(str(req));return key,code
    class FakeFile:
        def __init__(self,name=''):self.name=name
        def __truediv__(self,key):return FakeFile(key)
        def glob(self,s):return []
        def relative_to(self,root):return self.name
        def read_bytes(self):return b'sandbox'
        def __str__(self):return self.name
    def save(path,value):
        captured[path.name]=value
    with patch.object(online,'read',lambda p:[toy]),patch.object(online,'D',FakeFile()),patch.object(online,'call',respond),patch.object(online,'save',save),patch.object(online,'memories',reader):
        online.solve()
    end=captured['online_programs.json.gz'][0]
    assert len(calls)==len(ARMS)*len(NAMES)
    assert len({end['logs'][a][0]['key'] for a in ARMS})==1
    assert not end['logs']['full'][2]['valid']
    assert all(sum(not l['valid'] for l in end['logs'][a])==int(a=='full') for a in ARMS)
    return {'requests':len(calls),'equal_first_arm_requests':3,'arm_specific_histories_followed_after_first':12,
            'invalid_reply_fallback_on_its_own_path_only':True,'synthetic_fixture':True,'source_files_untouched':True}


if __name__=='__main__':
    write('independent_synthetic_history.json',run())


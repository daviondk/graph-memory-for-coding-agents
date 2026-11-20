"""Read-only offline audit of the final author-test and HumanEval+ results."""
import argparse
import ast
import concurrent.futures
import os
import subprocess
import sys

from common import ROOT, corpus, digest, read, run_suite, slug, src
from grade import paired, summary

def verify_corrected(folder, tasks, execute):
    def load(name):
        return read((folder / name).relative_to(ROOT))
    ids = load('roster.json')['ids']
    old = load('scores.json.gz')
    new = load('corrected_scores.json.gz')
    changes, helpers = {}, {}
    unique = {}
    assert len(old) == len(new) == len(ids)*7
    for initial, final in zip(old,new):
        i, arm = final['id'], final['arm']
        common = set(initial) - {'evaluated','hit','first_hit'}
        assert set(initial) == set(final)
        assert all(initial[k] == final[k] for k in common), (i,arm)
        key = i+'|'+arm
        outcome = final['evaluated']
        if outcome != initial['evaluated']:
            changes[key] = [initial['evaluated'],outcome]
        good = int(outcome['status']=='pass' and final['action'] in ('applied','control'))
        assert good == final['hit'] and int(good and not final['reread']) == final['first_hit']
        path = folder/'artifacts'/slug(i)/arm/'solution.py'
        if final['patch_sha'] is None:
            assert not path.exists() and outcome == {'status':'invalid_edit'}
            continue
        assert digest(path.read_bytes()) == final['patch_sha']
        unique_key = (i,final['patch_sha'])
        if unique_key in unique:
            assert unique[unique_key][1] == outcome
        unique[unique_key] = (path,outcome)
        if i in ('Python/50','Python/38') and good:
            def defs(text):
                return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(text).body if isinstance(node,ast.FunctionDef)}
            original = defs(src(tasks[i]))
            helper = next(iter(original))
            helpers[key] = original[helper] == defs(path.read_text(encoding='utf8')).get(helper)
    assert helpers == load('helper_integrity.json') and all(helpers.values())
    assert changes == load('namespace_differences.json')
    assert {k.split('|')[0] for k in changes} <= {'Python/50','Python/38'}
    corrected = load('corrected_results.json')
    assert summary(str(folder.relative_to(ROOT)) if folder != ROOT else '',ids,new,tasks) == corrected
    assert corrected['n_valid']==len(ids)
    if execute:
        def replay(item):
            (i,sha),(path,expected)=item
            entry = tasks[i]['entry_point']
            setup = ('import random\nrandom.seed(17112026)\n'
                     'globals().update({k:v for k,v in '+entry+'.__globals__.items() if not k.startswith("__")})\n')
            observed = run_suite(path,entry,setup+tasks[i]['test'])
            assert observed == expected, (i,sha,expected,observed)
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            list(pool.map(replay,unique.items()))
    print(f'corrected scores verified: {len(new)} records, {len(unique)} distinct programs, {len(ids)} original/canonical pairs',flush=True)

def verify_timing_receipts():
    saved = read('evalplus_timing_audit.json')
    differences = []
    total = 0
    for name in ('','transfer'):
        folder = ROOT/name
        def get(filename):
            return read((folder/filename).relative_to(ROOT))
        original = {(r['id'],r['arm']):r for r in get('corrected_scores.json.gz')}
        plus = get('evalplus_rows.json.gz')
        repeated = {(r['id'],r['hash']):r['observed'] for r in get('evalplus_replay.json.gz')}
        total += len(repeated)
        expected = {(r['id'],r['patch_sha']):r['evalplus'] for r in plus if r['patch_sha']}
        assert set(expected) == set(repeated)
        counts = {}
        for key,now in repeated.items():
            before = expected[key]
            if now != before:
                assert 'timeout' in (now['status'],before['status'])
                differences.append({'id':key[0],'hash':key[1],'original':before,'repeat':now})
        for row in plus:
            i,a,h = row['id'],row['arm'],row['patch_sha']
            counts.setdefault(a,[])
            counts[a].append(int(bool(h) and repeated[i,h]['status']=='pass' and original[i,a]['action'] in ('control','applied')))
        actual={'counts':{a:sum(v) for a,v in counts.items()},'pair':paired(counts['bundle'],counts['center'])}
        assert actual==saved['repeat_results'][name or 'primary']
        first_timeouts={r['id'] for r in plus if r['evalplus']['status']=='timeout'}
        safe_ids=[i for i in get('roster.json')['ids'] if i not in first_timeouts]
        scored={(r['id'],r['arm']):r['plus_hit'] for r in plus}
        b=[scored[i,'bundle'] for i in safe_ids]
        c=[scored[i,'center'] for i in safe_ids]
        computed={'n':len(b),'excluded':sorted(first_timeouts),'bundle':sum(b),'center':sum(c),'paired':paired(b,c)}
        assert computed==read('evalplus_timeout_sensitivity.json')[name or 'primary']
    key=lambda d:(d['id'],d['hash'])
    assert sorted(differences,key=key)==sorted(saved['timeout_disagreements'],key=key)
    assert total==saved['distinct_physical_files_by_task']==407
    print(f'second timing pass verified: {total} distinct programs, {len(differences)} timing-dependent results',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',help='re-run corrected and HumanEval+ tests against the actual serialized programs')
    parser.add_argument('--tokens',action='store_true',help='recount all memory packets with the saved tokenizer')
    args=parser.parse_args()
    os.environ['OPENBLAS_NUM_THREADS']=os.environ['OMP_NUM_THREADS']='1'
    def audit(script,flags):
        subprocess.run([sys.executable,'-B',str(ROOT/script),*flags],check=True)
    audit('verify.py',['--tokens'] if args.tokens else [])
    tasks=corpus()
    for folder in (ROOT,ROOT/'transfer'):
        verify_corrected(folder,tasks,args.execute)
    audit('verify_plus.py',['--execute'] if args.execute else [])
    verify_timing_receipts()
    print('all final audits passed',flush=True)

if __name__=='__main__':
    main()

import collections,itertools,shutil,subprocess,sys,tempfile
from common import *
def recompute_lru():
    src=list(rows(INPUT));q=read('results.json');n=collections.Counter();tot=collections.defaultdict(collections.Counter)
    for t in src:
        history={};states={k:[] for k in [1,2,4]}
        n.update(trajectories=1,literal_calls=len(t['literal_calls']),shell_calls=t['shell_calls'],edits=t['edits'])
        for tick,ed,x,terms in t['literal_calls']:
            old=x in history;stale=old and history[x]!=ed;n['cmd_repeat']+=old;n['cmd_after_edit']+=stale
            for k,r in states.items():
                h=x in r;tot[k].update(hits=h,after_edit_hits=h and stale,enrollments=not h,metadata_updates=1)
                if h:r.remove(x)
                r.append(x);r[:]=r[-k:]
            history[x]=ed
    for key,v in n.items():assert v==q['denominators']['all'][key]
    for k,v in tot.items():
        assert all(q['cohorts']['all'][f'cmd/{k}/lru'][m]==s for m,s in v.items())
    return n
def uniform_check():
    # Exhaust all equally likely ranks and compare joint any-hit/multiple-key probabilities.
    from grade import expected_hit
    for n in range(1,7):
        for k in (1,2,4):
            for m in range(n+1):
                allr=list(itertools.permutations(range(n)))
                p=sum(bool(set(rank[:k])&set(range(m))) for rank in allr)/len(allr)
                assert abs(p-expected_hit(n,m,k))<1e-12
def main():
    sourcecheck()
    n=recompute_lru();uniform_check()
    from matched import check_formula
    check_formula()
    targets=['decisions.jsonl.gz','trajectory.jsonl.gz','projects.json','results.json','matched_results.json']
    with tempfile.TemporaryDirectory(prefix='admission6-') as tmp:
        root=pathlib.Path(tmp)/'admission';root.mkdir()
        shutil.copyfile(INPUT,root.parent/'exposure.jsonl.gz')
        for name in ['PROTOCOL.md','MATCHED_PRELOCK.md','common.py','policies.py','run.py','grade.py','matched.py','design_lock.json','matched_design.json','calibration_lock.json']:
            shutil.copyfile(ROOT/name,root/name)
        for script in ['run.py','grade.py','matched.py']:
            subprocess.run([sys.executable,'-B',str(root/script)],cwd=root,check=True,stdout=subprocess.DEVNULL)
        equality={t:digest((root/t).read_bytes())==digest((ROOT/t).read_bytes()) for t in targets}
        assert all(equality.values())
    out=dict(full_clean_directory_rebuild=equality,independent_full_command_LRU_all_capacities=True,enum_uniform_bottomk_ranks_through_6_keys=True,enum_uniform_key_LRU_masks=True,census=n,source_sha=digest(INPUT.read_bytes()),decision_sha=digest((ROOT/'decisions.jsonl.gz').read_bytes()))
    write('verification.json',out); print(canon(out))
if __name__=='__main__':main()


"""Deterministic metadata-only eligibility. Reference content is used only for diff statistics."""
from pathlib import Path
import hashlib,json,re,subprocess,tarfile,os
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent
V=Path(os.environ.get('VIBE_CHECKOUT','D:/CodexResearch/x20-official-vibe/VibeMemBench'))
CACHE=D/'evaluator'/'archive'
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def rows():
    p=V/'benchmark/test.parquet'
    assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()=='22238743ca143276e3ff4616f569b3921c42945bfee1a6aa8fa376a02feebb98'
    return sorted(pq.read_table(p).to_pylist(),key=lambda r:(digest('R38-target-v1|'+r['instance_id']),r['instance_id']))
def ids(r):return sorted(p.parent.name for p in (V/'benchmark/history/python'/r['repo'].replace('/','__')).glob('*/*.traj.json') if p.parent.name!=r['instance_id'])
def paths(p):return [m[1] for m in re.findall(r'^diff --git a/(.+?) b/(.+?)$',p,re.M)]
def eligible(r):
    if r['language'].lower()!='python':return 'language'
    if r['repo'].lower()=='ipython/traitlets':return 'previous_repository'
    if not r['license'] or not re.fullmatch('[0-9a-f]{40}',r['base_commit']):return 'missing_metadata'
    cf=paths(r['patch']); n=sum(1 for s in r['patch'].splitlines() if s.startswith(('+','-')) and not s.startswith(('+++','---')))
    if not 1<=len(cf)<=4 or any(not p.endswith('.py') for p in cf) or n>240:return 'implementation_patch_scope'
    if not paths(r['test_patch']):return 'no_test_patch'
    if not (1<=len(r['FAIL_TO_PASS'])<=8 and 1<=len(r['PASS_TO_PASS'])<=160):return 'controls_count'
    if len(set(ids(r)))<3:return 'history_count'
    return 'review'
def main():
    for i,r in enumerate(rows()):
        reason=eligible(r)
        if reason=='review':
            print(i,r['instance_id'],r['license'],len(set(ids(r))),r['problem_statement'][:210].replace('\n',' ').encode('ascii','replace').decode())
if __name__=='__main__':main()
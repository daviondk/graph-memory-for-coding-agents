"""Offline trust-chain audit that runs without the original models, Git, TextWorld or Docker."""
from pathlib import Path
from collections import Counter
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
def sha(p):
    with p.open('rb') as fp:
        h=hashlib.sha256()
        for v in iter(lambda:fp.read(1048576),b''):h.update(v)
        return h.hexdigest()
def read(p):return json.loads((ROOT/p).read_bytes())
def run(args):
    cp=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,capture_output=True)
    if cp.returncode:raise RuntimeError(cp.stderr.decode('utf8','replace')[-2000:])
def main():
    inventory=ROOT/'MANIFEST.sha256.json'
    if inventory.exists():
        for f,d in read('MANIFEST.sha256.json').items():assert sha(ROOT/f)==d,f
    for d in ('compact','validity','procedure'):
        run([ROOT/d/'verify.py'])
    run([ROOT/'compact/path_control/score_paths.py','--verify'])
    run([ROOT/'procedure/cost/audit.py'])
    run([ROOT/'repair/generalization/offline_verify.py'])
    run([ROOT/'validity/environment/check.py'])
    for d in ('repair','alfworld'):
        before=(ROOT/d/'results.json').read_bytes()
        run([ROOT/d/'score.py'])
        assert (ROOT/d/'results.json').read_bytes()==before
    before=(ROOT/'alfworld/transfer_results.json').read_bytes();run([ROOT/'alfworld/transfer_score.py'])
    assert (ROOT/'alfworld/transfer_results.json').read_bytes()==before
    run([ROOT/'alfworld/checks.py','--final'])
    run([ROOT/'alfworld/text_only/audit.py','--check'])
    run([ROOT/'alfworld/text_only/failure_memory/verify.py','--check'])
    run([ROOT/'procedure/failure_replay/evaluate.py','--verify'])
    for entries in read('RESULTS_INDEX.json').values():
        for entry in entries:assert sha(ROOT/entry['file'])==entry['sha256']
    native=read('runtime/verified.json')['actual_by_experiment']
    events={e['id']:e for l in (ROOT/'runtime/requests.jsonl').read_text().splitlines() if (e:=json.loads(l))}
    used=set()
    for k,folder,req in [('repair','repair/calls','payload'),('planner','alfworld/planner_calls','request')]:
        sums=Counter()
        for p in (ROOT/folder).glob('*.json'):
            call=json.loads(p.read_bytes());rep=call['response'];e=events[rep['id']];assert e['id'] not in used;used.add(e['id'])
            assert e['seed']==call[req]['seed']==17112026 and e['usage']==rep['usage'] and e['max_output']==call[req]['max_tokens'] and e['reason_chars']==0
            assert e['message_sha256']==hashlib.sha256(json.dumps(call[req]['messages'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            sums.update({m:e['usage'][m] for m in ('prompt_tokens','completion_tokens')});sums['calls']+=1
        assert sums==native[k]
    assert len(used)==len(events)
    for f,v in read('upstream/sources.json').items():assert sha(ROOT/'upstream'/f)==v['sha256']
    print('PASS — source digests, published-trace & version checks, repair + ALFWorld scoring, transfer and native receipts.')
if __name__=='__main__':main()

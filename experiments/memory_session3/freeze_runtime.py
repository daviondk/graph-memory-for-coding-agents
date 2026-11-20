"""Capture receipts for exactly this round. Never includes credentials or user's unrelated files."""
import hashlib,json,shutil
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[2];rt=BASE/'x20-3-27b-runtime';old=BASE/'x20-qwen38-27b'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'runtime';out.mkdir(exist_ok=True)
    for name in ('model_receipt.json','runtime_receipt.json'):shutil.copy2(old/name,out/name)
    for name in ('managed_server.py','seed_proxy.py','resource_watch.py','service-resumed.json','requests.jsonl','guard-resumed.jsonl','resource-resumed.jsonl','resumed-native.log'):
        shutil.copy2(rt/name,out/name)
    events=[json.loads(l) for l in (out/'requests.jsonl').read_text().splitlines()]
    assert len({e['id'] for e in events})==len(events)
    seen={e['id']:e for e in events};used=set();tot={}
    for branch,folder,body,response in [('repair','repair/calls','payload','response'),('planner','alfworld/planner_calls','request','response')]:
        totals=Counter()
        for f in sorted((ROOT/folder).glob('*.json')):
            x=read(f);rep=x[response]; req=x[body];e=seen[rep['id']]
            assert rep['id'] not in used;used.add(rep['id'])
            assert e['seed']==17112026 and e['temperature']==0 and not e['chat_template_thinking']
            assert e['max_output']==req['max_tokens'] and e['usage']==rep['usage'] and e['reason_chars']==0
            assert e['message_sha256']==hashlib.sha256(json.dumps(req['messages'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            totals.update({k:rep['usage'][k] for k in ('prompt_tokens','completion_tokens')});totals['calls']+=1
        tot[branch]=totals
    assert used==set(seen)
    guard=[json.loads(l) for l in (out/'guard-resumed.jsonl').read_text().splitlines()]
    tele=[json.loads(l) for l in (out/'resource-resumed.jsonl').read_text().splitlines()]
    (out/'verified.json').write_text(json.dumps({'actual_by_experiment':tot,'stops_for_headroom':sum(e['stop'] for e in guard),
        'telemetry_samples':len(tele),'peak_GPU_MiB_all_processes':max(r['gpu_used_MiB'] for r in tele if r['gpu_used_MiB'] is not None),
        'min_host_available_MiB':min(r['physical_available_bytes'] for r in tele)/2**20},indent=1))
    print((out/'verified.json').read_text())
if __name__=='__main__':main()

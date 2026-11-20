"""Capture and independently cross-check every native call in this research batch."""
import collections,gzip,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)

def verify(out):
    ev=[json.loads(x) for x in (out/'requests.jsonl').read_text().splitlines()]
    seen={e['id']:e for e in ev};assert len(seen)==len(ev)
    used=set();tot={}
    for name,folder in [('original','handoff/calls'),('clean','handoff/clean/calls'),('permuted_control','handoff/shuffle/calls'),('strict_attribution','handoff/strict/calls')]:
        count=collections.Counter()
        for f in sorted((ROOT/folder).glob('*.gz')):
            x=read(f);rep=x['response'];req=x['request'];e=seen[rep['id']]
            assert rep['id'] not in used
            used.add(rep['id'])
            assert e['seed']==17112026 and e['temperature']==0 and not e['chat_template_thinking']
            assert e['max_output']==12==req['max_tokens'] and e['usage']==rep['usage'] and e['reason_chars']==0
            assert e['http_status']==200 and not e['tool_calls']
            assert e['message_sha256']==hashlib.sha256(json.dumps(req['messages'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            count.update({k:rep['usage'][k] for k in ('prompt_tokens','completion_tokens')})
            count['calls']+=1
        tot[name]=dict(count)
    assert used==set(seen)
    telemetry=[json.loads(x) for x in (out/'resource-resumed.jsonl').read_text().splitlines()]
    guards=[json.loads(x) for x in (out/'guard-resumed.jsonl').read_text().splitlines()]
    native_log=(out/'resumed-native.log').read_text(encoding='utf8',errors='replace')
    return {'actual_by_experiment':tot,'native_calls':len(ev),'all_saved_responses_success':True,
            'cuda_illegal_access_incidents':native_log.count('CUDA error: an illegal memory access was encountered'),
            'headroom_stops':sum(e['stop'] for e in guards),'telemetry_samples':len(telemetry),
            'peak_gpu_all_processes_MiB':max(r['gpu_used_MiB'] for r in telemetry if r['gpu_used_MiB'] is not None),
            'min_host_available_MiB':min(r['physical_available_bytes'] for r in telemetry)/2**20}

def main():
    base=ROOT.parents[2]
    runtime=base/'x20-4-27b-runtime'
    model=base/'x20-qwen38-27b'
    out=ROOT/'runtime';out.mkdir(exist_ok=True)
    for f in ('model_receipt.json','runtime_receipt.json'):
        shutil.copy2(model/f,out/f)
    for f in ('managed_server.py','seed_proxy.py','resource_watch.py','service-resumed.json','service-before-cuda-restart.json','requests.jsonl','guard-resumed.jsonl','resource-resumed.jsonl','resumed-native.log'):
        shutil.copy2(runtime/f,out/f)
    result=verify(out);(out/'verified.json').write_text(json.dumps(result,indent=1))
    print(result)
if __name__=='__main__':main()

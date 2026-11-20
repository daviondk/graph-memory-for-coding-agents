"""Separate physical GPU cost from the cost of each reader run in isolation."""
import csv
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def main():
    rr={r['payload_sha256']:r for r in (json.loads(x) for x in (ROOT/'calls.jsonl').read_text(encoding='utf8').splitlines())}
    parts={}
    for arm in ['hyb_real','online_fields']:
        ds=[z for z in read('blind_decisions.json') if z['arm']==arm]
        ran=[rr[z['payload_sha256']] for z in ds if z['payload_sha256']]
        parts[arm]={'questions':len(ds),'calls':len(ran),'prompt_tokens':sum(r['usage']['prompt_tokens'] for r in ran),'completion_tokens':sum(r['usage']['completion_tokens'] for r in ran),'fallbacks':sum(z['valid'] is False for z in ds),'seconds_summed':sum(r['seconds'] for r in ran)}
    costs={'per_independent_method':parts,'physical_gpu_calls':len(rr),'reused_identical_prompts':sum(z['calls'] for z in parts.values())-len(rr)}
    (ROOT/'costs.json').write_text(json.dumps(costs,indent=1)+'\n',encoding='utf8')
if __name__=='__main__':main()


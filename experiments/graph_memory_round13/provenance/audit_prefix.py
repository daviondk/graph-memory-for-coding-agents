"""Verify temporal accessibility against literal prefixes, independent of any oracle labels."""
import json
from common13 import D,R12,read,dump,digest,sha
from extract import pairs,V
def main():
    rows=read(D/'features.json.gz');notes={obs['iid']+':'+obs['tool_call_id']:obs for obs in read(R12/'keys.json')};roster={q['iid']:q for q in read(R12/'roster.json')};seen={};evidence=0
    for r in rows:
        t=r['iid'];idx=r['step'];p=V/'benchmark'/roster[t]['file']
        if t not in seen:seen[t]=json.loads(p.read_bytes())['messages']
        full=seen[t];pre=full[:idx]
        actual=[(i,c,sha(z['extra'].get('raw_output','').encode('utf8',errors='replace')) if isinstance(z['extra'].get('raw_output'),str) else None) for i,c,z in pairs(pre) if isinstance(z.get('extra'),dict)]
        target=[(i,c,sha(z['extra'].get('raw_output','').encode('utf8',errors='replace')) if isinstance(z['extra'].get('raw_output'),str) else None) for i,c,z in pairs(full) if i<idx and isinstance(z.get('extra'),dict)]
        assert actual==target and len(actual)==r['prior_calls']
        steps=[s[0] for s in actual]
        for v in r['evidence']:
            assert v['step']<idx and v['step'] in steps and v['age']==len(steps)-steps.index(v['step'])
            evidence+=1
        assert full[idx]['tool_call_id']==notes[r['id']]['tool_call_id']
    dump(D/'prefix_verification.json',dict(notes=len(rows),tasks=len(seen),witnesses_temporally_available=evidence,literal_truncation_projections_identical=True))
if __name__=='__main__':main()
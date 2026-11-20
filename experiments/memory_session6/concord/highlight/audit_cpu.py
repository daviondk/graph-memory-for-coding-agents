"""Independently corroborate changed tool messages, using stock HTTP inputs only."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def read(p):return json.loads(gzip.decompress(p.read_bytes()))
def h(s):return hashlib.sha256(s.encode()).hexdigest()

def main():
    detail=[]
    cases=sorted((ROOT/'cpu').glob('*_replay.json.gz'))
    for p in cases:
        z=read(p); before={}
        events={e['request']:e for e in z['opportunities']['previous']}
        for step,key in enumerate(z['requests'],1):
            req=read(ROOT.parent/'calls'/(key+'.json.gz'))['request']
            current={m['tool_call_id']:m['content'] for m in req['messages'] if m.get('role')=='tool'}
            if step in events:
                e=events[step];tid=e['tool_id'];old=before[tid];new=current[tid]
                assert old!=new and e['correction'] in new and e['control'] in new
                detail.append(dict(id=z['id'],step=step,tool_call_id=tid,old_message_sha256=h(old),new_message_sha256=h(new),
                                   correction_already_elsewhere_in_old=e['correction'] in old,correction=e['correction'],control=e['control']))
            before.update(current)
    assert len(cases)==40
    result={'n':len(detail),'cases':len({e['id'] for e in detail}),'correction_already_elsewhere_in_old':sum(e['correction_already_elsewhere_in_old'] for e in detail),'details':detail}
    path=ROOT/'previous_message_audit.json'
    if path.exists():assert json.loads(path.read_bytes())==result
    else:path.write_text(json.dumps(result,indent=1,ensure_ascii=False),encoding='utf8')
    print({k:v for k,v in result.items() if k!='details'})

if __name__=='__main__':main()

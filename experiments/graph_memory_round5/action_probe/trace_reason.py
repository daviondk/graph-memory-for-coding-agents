"""Verify the static provenance of the write likely responsible for the six neighbor discrepancies."""
import json,re,shlex
from pathlib import Path
from acquire import D,W,rr,read,save,h
def main():
    d=read(D/'disagreements.json');assert len(d)==1;r=d[0];iid=r['instance'];at=r['step'];path=r['path'];raw=dict(rr(D/'raw_pairs.jsonl.gz'))[iid]
    q=next(q for k in range(8) for q in rr(W/f'source_{k}.jsonl.gz') if q['instance']==iid)
    ops=[]
    for t,extra in enumerate(raw[:at-1],1):
        if not extra:continue
        args=shlex.split(extra['command'])
        if len(args)!=4 or args[:2]!=['sed','-i'] or not args[-1].endswith(path):continue
        m=re.fullmatch(r'(?:\d+)?s/([^/]*)/([^/]*)/g?',args[2])
        if not m:continue
        before,after=m.groups()
        ops.append(dict(step=t,path=path,inserted_linebreaks=after.count('\\n')-before.count('\\n'),pattern_sha=h(before.encode()),execution_confirmed_by_exit=False))
    three=[o for o in ops if o['inserted_linebreaks']==3 and o['step']<at]
    assert three and sorted(r['observations'])==['91','92','93','94','95','98'] and all(-3 in r['observations'][n]['memory_matching_truth_offsets'] for n in ('95','98'))
    save('trace_reason.json',dict(instance=iid,at=at,path=path,other_shell_edits=ops,untracked_three_line_insert=three[-1]['step'],exact_distinctive_shift_observations=[95,98],neighbors=len(r['observations'])))
if __name__=='__main__':main()


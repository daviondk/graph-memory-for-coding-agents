"""Measure transcript-only red flags without paying for Git; already accessible past vs external read."""
import json,statistics,time
from common13 import D,R12,dump,read,obs,sha
from forecast13 import inside,contains,normalized,single_file
from extract import pairs,V
from witness import inspect_command
def decide(note,prior):
    q=note['key']
    for step,cmd,data in prior:
        if step>=note['step'] or data.get('returncode')!=0:continue
        raw=data.get('raw_output')
        if isinstance(raw,str) and single_file(cmd):
            for root,path,kind in inspect_command(cmd,note['repo']):
                if kind=='content' and root==q['root'] and inside(path,q) and any(contains(line,q) for line in normalized(raw)):return True
    return False
def main():
    notes=read(R12/'keys.json');roster={r['iid']:r for r in read(R12/'roster.json')};actual={f['id']:not f['trust']['prefix_red_flag'] for f in read(D/'features.json.gz')};jobs=[];costs=[]
    for iid in sorted({r['iid'] for r in notes}):
        r=roster[iid];p=V/'benchmark'/r['file'];t0=time.perf_counter_ns();raw=p.read_bytes();data=json.loads(raw);prior=[(i,c,k['extra']) for i,c,k in pairs(data['messages']) if isinstance(k.get('extra'),dict)];tn=time.perf_counter_ns()-t0
        jobs.append(dict(iid=iid,bytes=len(raw),load_parse_ns=tn));assert sha(raw)==r['sha']
        for row in (n for n in notes if n['iid']==iid):
            arr=[]
            for _ in range(5):
                t0=time.perf_counter_ns();pred=decide(row,prior);arr.append(time.perf_counter_ns()-t0)
            assert pred==actual[obs(row)]
            costs.append(dict(id=obs(row),elapsed_ns=arr))
    sums=sum(statistics.median(r['elapsed_ns']) for r in costs)/1e6
    dump(D/'prefix_cost.json',dict(standalone_prefix_ms=sums,external_archive_parse_ms=sum(r['load_parse_ns'] for r in jobs)/1e6,external_archive_bytes=sum(r['bytes'] for r in jobs),tasks=jobs,per_note=costs))
if __name__=='__main__':main()
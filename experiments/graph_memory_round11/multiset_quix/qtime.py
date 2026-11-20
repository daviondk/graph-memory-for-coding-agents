"""End-to-end read/write cost on every QuixBugs snapshot at primary capacity."""
import base64,statistics,time,platform
from qutil import Q,put,load
from qbuild import state,prepare,METHODS
from exact import direct
from reader import read
def measured(fn):
    fn();t=time.process_time_ns();w=time.perf_counter_ns();count=0
    while time.process_time_ns()-t<125000000:
        for _ in range(8):fn()
        count+=8
    return dict(cpu_ns=(time.process_time_ns()-t)/count,wall_ns=(time.perf_counter_ns()-w)/count,n=count)
def main():
    rows=[];b=256
    for p in sorted((Q/'old').glob('*.gz')):
        original=load(p);data=load(Q/'states'/p.name)
        changed=list(map(str,load(Q/'future'/p.name)['changed']))
        n=len(original['names']);ss=[set(map(str,s)) for s in original['sets']];empty=(ss,{},[],[],[])
        for arm in METHODS:
            def build():
                if arm=='r9':
                    names=[set(map(str,w)) for w in original['sets']]
                    ready=names,{},[],[],[]
                elif arm=='always':ready=empty
                else:ready=prepare(original)
                return state(arm,b,0,ready)[0]
            matches=[r for r in data['states'] if r[0]==b and r[1]==0 and r[2]==arm]
            raw=base64.b64decode(matches[0][3]);assert build()==raw
            rows.append(dict(task=original['task'],direction=original['direction'],arm=arm,b=b,write=measured(build),read=measured(lambda:direct(raw,changed))))
    summary={a:{k:statistics.median(r[k]['cpu_ns'] for r in rows if r['arm']==a)/1000 for k in ['write','read']} for a in METHODS}
    put(Q/'timings.json',dict(platform=platform.platform(),capacity=b,summary_us=summary,rows=rows))
if __name__=='__main__':main()
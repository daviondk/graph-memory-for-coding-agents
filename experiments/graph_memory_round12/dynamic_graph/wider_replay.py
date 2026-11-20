"""Create an isolated secondary run from the frozen primary implementation."""
from collections import Counter
from pathlib import Path
import os,shutil,subprocess,sys
from util12 import D,R10,load,dump,event_raw,digest,sha
import importlib.util
spec=importlib.util.spec_from_file_location('r12prepare',D/'prepare.py'); local_prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(local_prepare);symbols=local_prepare.symbols
TARGET=D/'wide'
def main():
    if (TARGET/'state_seal.json').exists():raise RuntimeError('Use a fresh working copy to rebuild')
    roster=load(TARGET/'roster.json');old=load(TARGET/'trace_2.8.8.json');new=load(D/'trace_3.5.json')
    v=[symbols(D/'vendor'/version) for version in ['2.8.8','3.5']]
    astset={w for w in set(v[0])|set(v[1]) if v[0].get(w)!=v[1].get(w)}
    stats={};allnew=Counter();allgone=Counter()
    for module,chosen in roster['modules'].items():
        t=Path(module).stem;ids=sorted(k for k in chosen if all(z['status'].get(k,{}).get('call')=='passed' and z['rows'].get(k) for z in [old,new]))
        if not ids:continue
        evs=[];before={};newcnt=Counter();gonecnt=Counter();noop=0
        for phase,ver in enumerate([old,new]):
            for k in sorted(ids,key=lambda f:digest(f'R12-order-{phase}|'+f)):
                words=ver['rows'][k];i=ids.index(k);rr=set(words);prev=before.get(i,set())
                if phase:newcnt.update(rr-prev);gonecnt.update(prev-rr);noop+=int(rr==prev)
                before[i]=rr
                evs.append(dict(step=len(evs),phase=phase,i=i,words=words,archive_bytes=4+len(event_raw(words))))
        union=sorted(set().union(*(set(z['words']) for z in evs)))
        absent=['__r12_absent__/'+digest(t+'|'+str(j)) for j in range(32)]
        dump(TARGET/'events'/(t+'.json.gz'),dict(task=t,n=len(ids),names=ids,events=evs))
        dump(TARGET/'probes'/(t+'.json.gz'),dict(keys=union+absent,guaranteed_absent=absent,changed_definitions=sorted(set(union)&astset)))
        allnew.update(newcnt);allgone.update(gonecnt)
        stats[t]=dict(n=len(ids),noops=noop,absent_in_rerun=[k for k in chosen if k not in ids],added=sum(newcnt.values()),removed=sum(gonecnt.values()),unique_added=len(newcnt),unique_removed=len(gonecnt))
    data=dict(cohorts=stats,unavailable=roster['unavailable'],added=allnew,removed=allgone,files={str(p.relative_to(D)):sha(p) for p in [D/'trace_3.5.json',TARGET/'trace_2.8.8.json',D/'FAR_RELEASE_PROTOCOL.md',D/'wider_replay.py',TARGET/'roster.json',TARGET/'release.json']})
    dump(TARGET/'input_receipt.json',data)
    for name in ['store12.py','write.py','read.py','dictionary.py','grade12.py','ADDITIONAL_CONTROL.md','EXACT_CONTROL.md']:
        shutil.copyfile(D/name,TARGET/name)
    (TARGET/'util12.py').write_text((D/'util12.py').read_text(encoding='utf8').replace("D.parents[1]/'graph_memory_round10'","D.parents[2]/'graph_memory_round10'"),encoding='utf8')
    shutil.copyfile(D/'wider_replay.py',TARGET/'prepare.py')
    (TARGET/'PROTOCOL.md').write_text((D/'FAR_RELEASE_PROTOCOL.md').read_text(encoding='utf8')+'\n'+(D/'PROTOCOL.md').read_text(encoding='utf8'),encoding='utf8')
    for script in ['write.py','dictionary.py','read.py','grade12.py']:
        proc=subprocess.run([sys.executable,script],cwd=TARGET,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (TARGET/(script+'.log')).write_bytes(proc.stdout)
        assert proc.returncode==0,(script,proc.stdout[-900:])
if __name__=='__main__':main()
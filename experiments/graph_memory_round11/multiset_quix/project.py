"""Separate old graph and future inputs; lock the local QuixBugs provenance."""
from pathlib import Path
from difflib import SequenceMatcher
from qutil import Q,R9,put,load,sha

def diff_lines(old,new):
    a=[line.rstrip() for line in old.splitlines()];b=[line.rstrip() for line in new.splitlines()]
    ops=SequenceMatcher(None,a,b,autojunk=False).get_opcodes(); changed=set();changes=[]
    for name,i,j,k,h in ops:
        if name=='equal':continue
        affected=list(range(i+1,j+1)) if i!=j else [x for x in (i,i+1) if 1<=x<=len(a)]
        changed.update(affected);changes.append([name,i,j,k,h,affected])
    return sorted(changed),changes
def main():
    native=R9/'agentvalue'/'tasks';files={};cases=0
    for task in sorted(native.iterdir()):
        if not task.is_dir():continue
        bundle={}
        for tag in ['base','gold']:
            inp=task/tag/'checkout'/'python_programs'/(task.name+'.py');trace=task/tag/'testdata'/'trace.json.gz'
            assert inp.exists() and trace.exists()
            files[str(inp.relative_to(R9))]=sha(inp);files[str(trace.relative_to(R9))]=sha(trace)
            records=load(trace)['records']
            bundle[tag]=(inp.read_text(encoding='utf-8'),records)
        for a,b in [('base','gold'),('gold','base')]:
            text,old=bundle[a];new,after=bundle[b];names=sorted(old);assert names==sorted(after)
            sets=[sorted(set(old[k]['lines'])) for k in names]
            assert all(i>0 for s in sets for i in s)
            tag=task.name+'_'+a;cases+=1
            put(Q/'old'/f'{tag}.json.gz',dict(task=task.name,direction=a,names=names,sets=sets))
            changed,ops=diff_lines(text,new)
            put(Q/'future'/f'{tag}.json.gz',dict(task=task.name,direction=a,changed=changed,operations=ops,labels=[[old[k]['status'],after[k]['status']] for k in names]))
    assert cases==18
    put(Q/'native_inputs.json',files)
if __name__=='__main__':main()
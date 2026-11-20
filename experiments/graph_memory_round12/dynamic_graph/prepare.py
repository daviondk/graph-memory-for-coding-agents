"""Use past native executions to construct online event records; separate evaluation panel."""
import ast
from util12 import D,dump,load,sha,event_raw,digest
def symbols(root):
    out={}
    class Definition(ast.NodeVisitor):
        def __init__(self,file):self.path=file;self.prefix=''
        def nested(self,obj,want):
            prior=self.prefix;ident=self.prefix+obj.name
            if want:out[self.path+'|'+ident]=ast.dump(obj,include_attributes=False)
            self.prefix=ident+('.<locals>.' if want else '.')
            self.generic_visit(obj);self.prefix=prior
        def visit_ClassDef(self,node):self.nested(node,False)
        def visit_FunctionDef(self,node):self.nested(node,True)
        visit_AsyncFunctionDef=visit_FunctionDef
    for file in sorted((root/'networkx').rglob('*.py')):
        rel=file.relative_to(root).as_posix()
        if '/tests/' in rel or 'test_' in file.name or 'conftest' in file.name:continue
        Definition(rel).visit(ast.parse(file.read_text(encoding='utf8')))
    return out
def main():
    vs=['3.4.2','3.5'];audit={}
    versions=[load(D/f'trace_{v}.json') for v in vs]
    repeated=load(D/'repeat_3.5.json')
    changed_repeats=[k for k in versions[1]['rows'] if versions[1]['rows'][k]!=repeated['rows'].get(k)]
    asts=[symbols(D/'vendor'/v) for v in vs]
    definition_changes=sorted(w for w in set(asts[0])|set(asts[1]) if asts[0].get(w)!=asts[1].get(w))
    common=load(D/'roster.json')['modules'];by={}
    for mod,tests in common.items():
        task=mod.split('/')[-1][:-3];eligible=[];skip=[]
        for t in tests:
            if all(z['status'].get(t,{}).get('call')=='passed' and z['rows'].get(t) for z in versions):eligible.append(t)
            else:skip.append(t)
        assert len(eligible)>=4
        names=sorted(eligible);events=[];previous={};added=removed=identical=0
        for phase,z in enumerate(versions):
            for t in sorted(eligible,key=lambda w:digest(f'R12-order-{phase}|'+w)):
                vals=z['rows'][t];old=previous.get(t,[]);new=set(vals);past=set(old)
                step=len(events);rid=names.index(t);record=event_raw(vals)
                events.append(dict(step=step,i=rid,words=vals,archive_bytes=4+len(record),phase=phase))
                if phase:
                    added+=len(new-past);removed+=len(past-new);identical+=int(new==past)
                previous[t]=vals
        total=sorted(set().union(*(set(r['words']) for r in events)))
        cv=sorted(set(total)&set(definition_changes));absent=['__r12_absent__/'+digest(task+'|'+str(j)) for j in range(32)]
        dump(D/'events'/(task+'.json.gz'),dict(task=task,n=len(names),names=names,events=events))
        dump(D/'probes'/(task+'.json.gz'),dict(keys=total+absent,changed_definitions=cv,guaranteed_absent=absent))
        by[task]=dict(n=len(names),records=len(events),known_keys=len(total),intersection_changed=len(cv),new_edges=added,removed_edges=removed,noop_replacements=identical,excluded=skip)
    sources=[D/f'trace_{v}.json' for v in vs]+[D/'repeat_3.5.json',D/'PROTOCOL.md',D/'roster.json',D/'release_lock.json',D/'collect.py']
    dump(D/'input_receipt.json',dict(files={p.name:sha(p) for p in sources},cohorts=by,determinism_mismatching_tests=changed_repeats,actual_changed_definitions=len(definition_changes)))
if __name__=='__main__':main()
"""Bounded source memories; inputs are the physical source read and a prior agent-chosen focus."""
import ast
from common import *
BUDGET=80
ARMS=('none','recent','center','bundle','full')
def packets(source,focus,status,token_count):
    data=lines(source)
    ids=list(range(1,len(data)+1))
    window=[i for i in ids if abs(i-focus)<=2]
    recent=(numbered(source)+'\n'+numbered(source,window)+'\nPublic example run: '+status).splitlines()
    retained=[]
    for l in reversed(recent):
        cand=[l]+retained
        if token_count('\n'.join(cand))>BUDGET:break
        retained=cand
    order=sorted(ids,key=lambda i:(abs(i-focus),i))
    def contiguous():
        ans=[]
        for i in order:
            trial=sorted(ans+[i])
            if token_count(numbered(source,trial))>BUDGET:break
            ans=trial
        return numbered(source,ans)
    tree=ast.parse(source)
    stmts=[n for n in ast.walk(tree) if isinstance(n,ast.stmt) and n.lineno<=focus<=n.end_lineno]
    stmts.sort(key=lambda n:(n.end_lineno-n.lineno,-n.col_offset))
    def header(n):
        if hasattr(n,'body') and isinstance(n.body,list) and n.body and isinstance(n.body[0],ast.stmt):
            return list(range(n.lineno,max(n.lineno+1,n.body[0].lineno)))
        return list(range(n.lineno,n.end_lineno+1))
    groups=[]
    if stmts:
        groups.append(header(stmts[0]))
        for n in stmts[1:]:groups.append(header(n))
    groups.extend([[i] for i in order])
    chosen=set()
    for g in groups:
        trial=chosen|set(g)
        if token_count(numbered(source,sorted(trial)))<=BUDGET:chosen=trial
    return {'none':'','recent':'\n'.join(retained),'center':contiguous(),'bundle':numbered(source,sorted(chosen)),'full':numbered(source)}

def apply_edit(source,answer):
    text=answer.strip()
    if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
    try:op=json.loads(text)
    except ValueError:return None,'invalid_json'
    if not isinstance(op,dict) or set(op)!={'start','end','new'}:return None,'invalid_schema'
    lo,hi,new=op['start'],op['end'],op['new'];data=lines(source)
    if type(lo)!=int or type(hi)!=int or not 1<=lo<=hi<=len(data) or not isinstance(new,str) or len(new)>5000:return None,'invalid_range'
    updated='\n'.join(data[:lo-1]+new.rstrip('\n').splitlines()+data[hi:])+'\n'
    return updated,'no_change' if updated==source else 'applied'

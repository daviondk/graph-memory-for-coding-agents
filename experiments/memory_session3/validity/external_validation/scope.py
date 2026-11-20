"""Local source projections for observers; no current command outputs used."""
import ast, functools, hashlib
from pathlib import Path
from sources import tree,canon,sha
DEFS=(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)
def fp(s):return sha(s.encode())
def namespace(rel):
    a=rel[:-3].replace('/','.')
    return a.removesuffix('.__init__')
def find_origin(pkg,v,mod):
    if not mod:return None
    root=tree(pkg,v);m=mod.replace('.','/')
    for r in [m+'.py',m+'/__init__.py']:
        if (root/r).is_file():return r
    return None
def definitions(body,prefix,funcs,lines,bindings):
    for node in body:
        if isinstance(node,DEFS):
            q=prefix+node.name; funcs[q]=node
            lineno=min([node.lineno]+[d.lineno for d in node.decorator_list])
            lines[(q,lineno)]=node
            if not prefix:bindings.setdefault(node.name,[]).append(node)
            definitions(node.body,q+('.' if isinstance(node,ast.ClassDef) else '.<locals>.'),funcs,lines,bindings)
        elif not prefix:
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[a.asname or a.name.split('.')[0] for a in node.names]
            else:
                names=[a.id for a in ast.walk(node) if isinstance(a,ast.Name) and isinstance(a.ctx,ast.Store)]
            for n in set(names):bindings.setdefault(n,[]).append(node)
@functools.lru_cache(None)
def parsed(pkg,v,rel):
    path=tree(pkg,v)/rel
    if not path.is_file():return None
    data=path.read_bytes();t=ast.parse(data);fs={};ln={};b={}
    definitions(t.body,'',fs,ln,b)
    return sha(data),fs,ln,b
def origin_node(q,line,old,current):
    if (q,line) in old[2]:
        x=old[2][q,line]
        if current is old:return x
        return current[1].get(q)
    return None
def mask_paths(node,coverage):
    mask=set()
    def visit(n,path):
        if not isinstance(n,ast.AST):return
        for fld,v in ast.iter_fields(n):
            if isinstance(v,list):
                key=path+(fld,)
                if n is not node and fld in ('body','orelse','finalbody') and v and all(isinstance(k,ast.stmt) for k in v):
                    if not any(any(k.lineno<=i<=k.end_lineno for i in coverage) for k in v):
                        mask.add(key);continue
                for j,c in enumerate(v):visit(c,key+(j,))
            elif isinstance(v,ast.AST):visit(v,path+(fld,))
    visit(node,());return frozenset(mask)
def repr_node(node,mask):
    def visit(n,path):
        if path in mask:return '[untaken body]'
        if isinstance(n,ast.AST):return [type(n).__name__]+[[f,visit(v,path+(f,))] for f,v in ast.iter_fields(n)]
        if isinstance(n,list):return [visit(x,path+(i,)) for i,x in enumerate(n)]
        if isinstance(n,(bytes,complex)) or n is Ellipsis:return [type(n).__name__,repr(n)]
        return n
    return fp(canon(visit(node,())))
@functools.lru_cache(maxsize=None)
def masked(node,lines):
    return mask_paths(node,lines)
@functools.lru_cache(maxsize=None)
def signature(node,mask):
    return repr_node(node,mask)
@functools.lru_cache(None)
def references(node):
    names={x.id for x in ast.walk(node) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load)}
    attrs={(x.value.id,x.attr) for x in ast.walk(node) if isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name)}
    return names,attrs
def base_module(rel,node):
    cur=namespace(rel)
    if not rel.endswith('/__init__.py'):cur=cur.rpartition('.')[0]
    if node.level:
        names=cur.split('.')
        cur='.'.join(names[:len(names)-node.level+1])
        return '.'.join(filter(None,[cur,node.module]))
    return node.module or ''
@functools.lru_cache(None)
def dependency(pkg,v,rel,name,attribute,depth=0):
    src=parsed(pkg,v,rel);ns=[] if not src else src[3].get(name,[])
    if not ns:return '-'
    parts=[]
    for n in ns:
        if isinstance(n,DEFS):
            part=[type(n).__name__,n.name,[ast.dump(x) for x in n.decorator_list]]
            if isinstance(n,ast.ClassDef):part.extend(ast.dump(x) for x in n.bases)
            parts.append(part);continue
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            for a in n.names:
                if (a.asname or a.name.split('.')[0])!=name:continue
                if isinstance(n,ast.ImportFrom):
                    mod=base_module(rel,n)
                    child=find_origin(pkg,v,mod+'.'+a.name)
                    if child:nsrel=child;key=attribute
                    else:nsrel=find_origin(pkg,v,mod);key=a.name
                else:nsrel=find_origin(pkg,v,a.name);key=attribute
                d=dependency(pkg,v,nsrel,key,'',depth+1) if nsrel and key and depth<3 else ''
                parts.append([ast.dump(n),d])
            continue
        parts.append(ast.dump(n))
        if depth<2:
            names,_=references(n)
            parts.extend([k,dependency(pkg,v,rel,k,'',depth+1)] for k in sorted(names-{name}) if k in src[3])
    return fp(canon(parts))
@functools.lru_cache(None)
def guards(pkg,v,rel,node):
    names,attrs=references(node);src=parsed(pkg,v,rel)
    return tuple([(nm,'',dependency(pkg,v,rel,nm,'')) for nm in sorted(names) if nm in src[3]]+
                 [(nm,a,dependency(pkg,v,rel,nm,a)) for nm,a in sorted(attrs) if nm in src[3]])
def reuse(pkg,old,new,prior,next_entry):
    same=prior['entry']==next_entry
    module=(prior['entry'] or [None])[0]
    old_file=find_origin(pkg,old,module);new_file=find_origin(pkg,new,module)
    def checksum(ver,rel):
        obj=parsed(pkg,ver,rel) if rel else None
        return obj[0] if obj else None
    direct=same and old_file==new_file and checksum(old,old_file)==checksum(new,new_file)
    files={item[0] for item in prior['covered']}; files.update(f for f in [old_file] if f)
    dynamic=same and all(checksum(old,f)==checksum(new,f) for f in files)
    full=guarded=branch=same
    for rel,q,line,covered in prior['covered']:
        x=parsed(pkg,old,rel); y=parsed(pkg,new,rel)
        if not x or not y:full=guarded=branch=False;break
        if x[0]==y[0]:
            same_file=True
        else:same_file=False
        u=origin_node(q,line,x,x);v=origin_node(q,line,x,y)
        if not u or not v:
            # Nested anonymous scopes run inside the owning function. Explicitly cover it.
            parts=q.split('.<locals>.')
            if len(parts)>1:
                u=x[1].get('.<locals>.'.join(parts[:-1]));v=y[1].get('.<locals>.'.join(parts[:-1]))
        if not u or not v:
            full &= same_file;guarded &= same_file;branch &= same_file;continue
        match=same_file or signature(u,frozenset())==signature(v,frozenset())
        full &= match
        og=guards(pkg,old,rel,u)
        ok=all(dependency(pkg,new,rel,n,a)==h for n,a,h in og)
        guarded &= match and ok
        if branch and ok and not match:
            mask=masked(u,tuple(covered))
            branch=signature(u,mask)==signature(v,mask)
        else:branch &= ok
    return {'always_replay':False,'always_reuse':True,'direct_file':bool(direct),'dynamic_files':bool(dynamic),
            'scopes':bool(full),'scopes_guards':bool(guarded),'observed_branches_guards':bool(branch)}


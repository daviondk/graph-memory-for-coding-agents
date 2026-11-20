"""Finite-memory update rules. All commands supplied by the corpus are strings."""
import ast
import collections
import math
import re
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
AP = WORK / 'graph_memory_round5/action_probe'
sys.path.insert(0, str(AP))
import bounded as old

HIDDEN = '\0old:'
ARMS = ('r5', 'lru', 'invalidate', 'transport')
ROOT_CHANGE = re.compile(r'(?:^|[;&\n])\s*(?:cd|pushd|popd)\b')
SIMPLE_SUB = re.compile(r"(?:(\d+))?s/([^/]+)/([^/]*)/(g?)")


def next_root(root, raw):
    if raw:
        cmd = raw['command']
        if ROOT_CHANGE.search(cmd):
            root = False
        if re.fullmatch(r'\s*cd\s+/testbed/?\s*',cmd):
            root = True
    return root


def py_writes(code, clean):
    """Recognize literal path forms in file writes. Parse a bounded text, never run it."""
    try:
        module = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return []
    assignments = collections.defaultdict(list)
    for item in ast.walk(module):
        if isinstance(item, ast.Assign):
            for node in item.targets:
                if isinstance(node,ast.Name):
                    assignments[node.id].append(item.value)

    def literal(node, resolve=True):
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            return node.value
        if resolve and isinstance(node,ast.Name) and len(assignments[node.id])==1:
            return literal(assignments[node.id][0],False)
        if isinstance(node,ast.Call) and len(node.args)==1 and (
            isinstance(node.func,ast.Name) and node.func.id=='Path' or
            isinstance(node.func,ast.Attribute) and node.func.attr=='Path'
        ):
            return literal(node.args[0],False)
        return ''

    actions=[]
    for call in ast.walk(module):
        if not isinstance(call,ast.Call):
            continue
        func=call.func
        if isinstance(func,ast.Name) and func.id=='open' and call.args:
            mode = literal(call.args[1]) if len(call.args)>1 else next((literal(k.value) for k in call.keywords if k.arg=='mode'),'r')
            if any(m in mode for m in 'wax+'):
                actions.append((clean(literal(call.args[0])), 'append' if mode.startswith('a') else 'write',''))
        if isinstance(func,ast.Attribute) and func.attr in ('write_text','write_bytes','unlink','touch'):
            actions.append((clean(literal(func.value)), 'write',''))
    return actions


def mutations(raw,root):
    if not raw or raw['name']!='bash':
        return []
    cmd=raw['command'].strip()
    if not cmd or len(cmd)>65000:
        return []
    prefix=re.match(r'^cd\s+(/testbed(?:/[\w./-]*)?)\s*&&\s*',cmd)
    directory=''
    if prefix:
        directory=prefix[1].removeprefix('/testbed').strip('/')
        root=True
        cmd=cmd[prefix.end():]
    def clean(path):
        if directory and path and not path.startswith('/'):
            path=directory+'/'+path.removeprefix('./')
        return old.pol.clean(path,root)

    actions=[]
    here=re.fullmatch(r"""(?:python3?|python3?\s+-)\s*<<\s*['"]?(\w+)['"]?\s*\n(.*?)\n\1\s*""",cmd,re.S)
    if here:
        actions=py_writes(here[2],clean)
    else:
        first=cmd.split('\n',1)[0]
        try:
            lexer=shlex.shlex(first,posix=True,punctuation_chars=';&|<>')
            lexer.whitespace_split=True
            lexer.commenters=''
            args=list(lexer)
        except ValueError:
            return []
        if not args or any(t in ('|','||','&&',';','&') for t in args):
            return []
        tool=args[0]
        if tool=='sed' and len(args)==4 and args[1] in ('-i','--in-place'):
            actions=[(clean(args[-1]),'sed',args[2])]
        elif tool in ('cat','echo','printf'):
            for j,arg in enumerate(args[:-1]):
                if arg in ('>','>>'):
                    actions.append((clean(args[j+1]),'append' if arg=='>>' else 'write',''))
        elif tool in ('cp','mv') and len(args)==3 and all(not a.startswith('-') for a in args[1:]):
            actions=[(clean(args[-1]),'write','')]
            if tool=='mv':
                actions.append((clean(args[1]),'write',''))
        elif tool=='rm' and all(not a.startswith('-') or a=='-f' for a in args[1:]):
            actions=[(clean(v),'write','') for v in args[1:] if v!='-f']
        elif tool=='git' and args[1:3] in (['checkout','--'],['restore','--']):
            actions=[(clean(v),'write','') for v in args[3:]]
        elif cmd.startswith(('python -c ','python3 -c ')):
            try: full=shlex.split(cmd)
            except ValueError: full=[]
            if len(full)==3:
                actions=py_writes(full[2],clean)
    return list(dict.fromkeys((p,k,expr) for p,k,expr in actions if p))


def transform(text,kind,expr):
    """Return publicly retained coordinates and coordinates awaiting independent evidence."""
    if not text:
        return {},{}
    if kind=='append':
        last=max(text)
        return {n:v for n,v in text.items() if n<last},{last:text[last]}
    if kind=='sed':
        addr=re.fullmatch(r'(\d+)([aid])(?:\\(.*))?',expr)
        if addr:
            index,op=int(addr[1]),addr[2]
            if index>=1 and ((op=='d' and addr[3] is None) or (op in 'ai' and addr[3] is not None and '\\' not in addr[3])):
                if op=='d':
                    return {n-int(n>index):v for n,v in text.items() if n!=index},{}
                return {n+int(n>=index+(op=='a')):v for n,v in text.items()},{}
        sub=SIMPLE_SUB.fullmatch(expr)
        if sub and '\\' not in sub[3] and '\n' not in sub[3]:
            row=int(sub[1]) if sub[1] else None
            # Limit matching to literal GNU BRE characters plus a dot wildcard.
            simple=re.fullmatch(r"[\w .,:=()+/'\x22#\-]+",sub[2])
            pattern=re.compile(''.join('.' if c=='.' else re.escape(c) for c in sub[2])) if simple else None
            live={n:v for n,v in text.items() if row is not None and n!=row or pattern and not pattern.search(v[0])}
            return live,{n:v for n,v in text.items() if n not in live}
    return {},dict(text)


def restore(ghost,observed,live):
    """Two nearby unique old/new line anchors agree on a translation, without observed conflicts."""
    def coords(table):
        d=collections.defaultdict(list)
        for n,s in table.items():
            if sum(c.isalnum() for c in s)>=8:
                d[s].append(n)
        return d
    oldloc=coords({n:v[0] for n,v in ghost.items()})
    newloc=coords(observed)
    by_offset=collections.defaultdict(list)
    for s,ns in newloc.items():
        if len(ns)==len(oldloc.get(s,()))==1:
            n=oldloc[s][0]
            if abs(ns[0]-n)<=128:
                by_offset[ns[0]-n].append(n)
    proposed=collections.defaultdict(list)
    for shift,anchors in by_offset.items():
        anchors.sort()
        for left,right in zip(anchors,anchors[1:]):
            if right-left>24 or any(n not in ghost for n in range(left,right+1)):
                continue
            lo,hi=left,right
            while lo-1 in ghost and left-lo<8: lo-=1
            while hi+1 in ghost and hi-right<8: hi+=1
            if any(n+shift in observed and observed[n+shift]!=ghost[n][0] for n in range(lo,hi+1)):
                continue
            for n in range(lo,hi+1):
                dest=n+shift
                if dest>0 and dest not in live and dest not in observed:
                    proposed[dest].append(n)
    return {n:ghost[ns[0]] for n,ns in proposed.items() if len(set(ns))==1}


def advance(state,meta,event,t,extra_lines,ops,arm,stats):
    ss=state['rebase']
    _,args,obs=event
    p=old.anchor.rel(args.get('path'))
    if arm in ('invalidate','transport'):
        for path,kind,expr in ops:
            before=ss.pop(path,{})
            hidden=HIDDEN+path
            ss.pop(hidden,None)
            stats['writes']+=1
            stats['resident_writes']+=bool(before)
            stats['resident_pre_lines']+=len(before)
            if arm=='transport':
                live,ghost=transform(before,kind,expr)
                if live: ss[path]=live
                if ghost:
                    ss[hidden]=ghost
                    meta['center'][hidden]=meta['center'].get(path,0)
                    meta['paths'][hidden]=meta['paths'].get(path,0)
                stats['directly_retained']+=len(live)
                stats['quarantined']+=len(ghost)
        if arm=='transport' and p and (old.anchor.success(args.get('command'),p,obs) or args.get('command') in ('insert','undo_edit','create')):
            ss.pop(HIDDEN+p,None)
    old.anchor.anchored_advance(state,meta,event,t)
    shown=collections.defaultdict(dict)
    if args.get('command')=='view' and p:
        shown[p].update(old.anchor.printed(obs))
    groups=collections.defaultdict(list)
    for path,n,value,_ in extra_lines:
        ss.setdefault(path,{})[n]=[value,t]
        shown[path][n]=value
        groups[path].append(n)
    for path,ns in groups.items():
        meta['paths'][path]=t
        meta['visits'][path]+=1
        meta['center'][path]=(min(ns)+max(ns))*.5
    if arm=='transport':
        for path,values in shown.items():
            ghost=ss.get(HIDDEN+path)
            if ghost:
                new=restore(ghost,values,ss.get(path,{}))
                if new:
                    ss.setdefault(path,{}).update(new)
                    stats['anchor_restored']+=len(new)
                    # Retire a quarantine generation once its first local recovery has been applied.
                    ss.pop(HIDDEN+path,None)
